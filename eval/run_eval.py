"""The eval harness — runs the full pipeline over the labelled set and writes eval_report.md.

Model outputs are cached (model_cache) so re-running the report is FREE; pass --no-cache to
force fresh calls. The report's headline is the safety claim: zero clinical red flags
auto-answered, and 100% recall on reportable-injury candidates.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from vigil import config, db, respond, seed
from vigil.evaluate import compute_metrics, load_results_frame
from vigil.llm import get_client
from vigil.pipeline import persist_case, process_message
from vigil.retrieve import load_retriever
from vigil.schemas import EvalMetrics, Message

REPORT_PATH = config.ROOT / "eval" / "eval_report.md"


def ensure_seeded(conn) -> None:
    n = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    if n == 0:
        seed.reset_data(conn)
        seed.seed_corpus(conn)
        seed.seed_dataset(conn)


def clear_cases(conn) -> None:
    for table in ("audit_log", "mdr_drafts", "complaint_records", "cases"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def _cm_table(cm: list[list[int]]) -> str:
    (tn, fp), (fn, tp) = cm
    return (
        "| | predicted 0 | predicted 1 |\n"
        "|---|---:|---:|\n"
        f"| **actual 0** | {tn} | {fp} |\n"
        f"| **actual 1** | {fn} | {tp} |\n"
    )


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def render_report(metrics: EvalMetrics) -> str:
    cl, cp = metrics.clinical, metrics.complaint
    fn_empty = len(metrics.clinical_false_negatives) == 0
    safe = fn_empty and metrics.clinical_auto_sent == 0

    lines: list[str] = []
    lines.append("# Vigil — Eval Report\n")
    lines.append(
        f"_Model: `{config.TRIAGE_MODEL}` · prompt `{config.PROMPT_VERSION}` · "
        f"{metrics.n} messages · temperature {config.TEMPERATURE}_\n"
    )

    headline = (
        f"**Across {metrics.n} messages, {metrics.clinical_auto_sent} clinical red flags were "
        f"auto-answered, and the clinical red-flag detector caught {_pct(cl.recall)} of them "
        f"(reportable-injury recall {_pct(metrics.mdr_recall)} over {metrics.mdr_support} candidates).**"
    )
    lines.append("## Headline\n")
    lines.append(("✅ " if safe else "⚠️ ") + headline + "\n")

    lines.append("## Clinical red-flag detector (PRIMARY — recall is the safety metric)\n")
    lines.append(
        f"- **Recall: {_pct(cl.recall)}** (target ~100%)\n"
        f"- Precision: {_pct(cl.precision)}  ·  F1: {_pct(cl.f1)}  ·  positives in set: {cl.support}\n"
    )
    lines.append(_cm_table(cl.confusion))
    lines.append("")

    lines.append("### Dangerous misses (false negatives — must be empty)\n")
    if fn_empty:
        lines.append("None. ✅ No clinical red flag was missed.\n")
    else:
        for fnr in metrics.clinical_false_negatives:
            lines.append(f"- `{fnr['id']}` ({fnr['bucket']}): {fnr['text']}")
        lines.append("")

    lines.append("## Complaint detector (FDA 21 CFR 820.3(b))\n")
    lines.append(
        f"- Precision: {_pct(cp.precision)}  ·  Recall: {_pct(cp.recall)}  ·  "
        f"F1: {_pct(cp.f1)}  ·  positives: {cp.support}\n"
    )
    lines.append(_cm_table(cp.confusion))
    lines.append("")

    lines.append("## MDR-potential (reportable-injury candidates)\n")
    lines.append(f"- Recall over the {metrics.mdr_support} serious/MDR-candidate cases: **{_pct(metrics.mdr_recall)}**\n")

    lines.append("## Routing safety check\n")
    mark = "✅" if metrics.clinical_auto_sent == 0 else "❌"
    lines.append(f"- Clinical cases that were auto-sent: **{metrics.clinical_auto_sent}** (must be 0) {mark}\n")

    lines.append("## Per-bucket breakdown\n")
    lines.append("| bucket | n | clinical recall | complaint recall |\n|---|---:|---:|---:|")
    for bucket, b in sorted(metrics.per_bucket.items()):
        lines.append(f"| {bucket} | {b['n']} | {_pct(b['clinical_recall'])} | {_pct(b['complaint_recall'])} |")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Vigil eval harness.")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh model calls (spends tokens).")
    args = parser.parse_args()

    conn = db.init_db()
    ensure_seeded(conn)
    clear_cases(conn)
    if args.no_cache:
        conn.execute("DELETE FROM replies")
        conn.commit()

    retriever = load_retriever(conn)
    client = get_client()

    rows = conn.execute("SELECT id, raw_text, journey_stage FROM messages ORDER BY id").fetchall()
    print(f"Processing {len(rows)} messages ({'fresh' if args.no_cache else 'cached'})...")
    for i, r in enumerate(rows, 1):
        msg = Message(id=r["id"], raw_text=r["raw_text"], journey_stage=r["journey_stage"] or "unknown")
        res = process_message(client, msg, retriever=retriever, conn=conn, no_cache=args.no_cache)
        persist_case(conn, res)
        respond.ensure_reply(conn, client, msg, res.routing.routing_decision, res.top_chunk, no_cache=args.no_cache)
        if i % 20 == 0:
            print(f"  {i}/{len(rows)}")

    df = load_results_frame(conn)
    metrics = compute_metrics(df)
    report = render_report(metrics)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"\nWrote {REPORT_PATH}")
    print(f"  Clinical recall:   {metrics.clinical.recall * 100:.1f}%")
    print(f"  Clinical FNs:      {len(metrics.clinical_false_negatives)} (must be 0)")
    print(f"  Clinical auto-sent:{metrics.clinical_auto_sent} (must be 0)")
    print(f"  MDR recall:        {metrics.mdr_recall * 100:.1f}% over {metrics.mdr_support}")
    print(f"  Complaint F1:      {metrics.complaint.f1 * 100:.1f}%")


if __name__ == "__main__":
    main()
