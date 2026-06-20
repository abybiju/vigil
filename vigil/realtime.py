"""Live single-message ingestion: raw dict -> persist message -> run the full pipeline ->
persist case (+ MDR draft + reply) -> return a routing summary.

This is what a webhook handler calls per inbound message. It writes to the same SQLite DB
the Streamlit app reads, so processed cases appear in the dashboard in real time.
"""

from __future__ import annotations

import anthropic

from . import db, outbound, respond
from .ingest import ingest_message
from .pipeline import persist_case, process_message
from .retrieve import Retriever


def ingest_and_process(
    conn,
    client: anthropic.Anthropic,
    raw: dict,
    *,
    platform: str | None = None,
    retriever: Retriever | None = None,
    stage_mapping: dict[str, str] | None = None,
    no_cache: bool = False,
) -> dict:
    """Ingest one normalized message, triage/route/respond, and post the result back. Returns a summary."""
    if platform is not None:
        raw = {**raw, "platform": platform}
    msg = ingest_message(raw, stage_mapping=stage_mapping)

    db.insert(
        conn,
        "messages",
        {
            "id": msg.id,
            "source": msg.source,
            "channel": msg.channel,
            "received_at": msg.received_at,
            "customer_ref": msg.customer_ref,
            "order_ref": msg.order_ref,
            "journey_stage": msg.journey_stage,
            "raw_text": msg.raw_text,  # already PII-masked
            "platform": msg.platform,
            "external_id": msg.external_id,
        },
    )

    res = process_message(client, msg, retriever=retriever, conn=conn, no_cache=no_cache)
    case_id = persist_case(conn, res)
    reply = respond.ensure_reply(
        conn, client, msg, res.routing.routing_decision, res.top_chunk, no_cache=no_cache
    )

    held = res.routing.routing_decision in ("clinical_review", "vigilance_review")
    summary = {
        "message_id": msg.id,
        "case_id": case_id,
        "platform": msg.platform,
        "external_id": msg.external_id,
        "channel": msg.channel,
        "journey_stage": msg.journey_stage,
        "masked_text": msg.raw_text,
        "is_complaint": res.triage.is_complaint,
        "clinical_red_flag": res.clinical.clinical_red_flag,
        "potential_mdr": res.triage.potential_mdr,
        "severity": res.triage.severity,
        "routing_decision": res.routing.routing_decision,
        "reason": res.routing.reason,
        "held_for_human": held,
        "reply": reply.body if reply else None,
        "reply_grounded": bool(reply.grounded) if reply else False,
    }

    # Outbound: post the triage back to the source ticket (dry-run by default; human gate enforced).
    summary["outbound"] = _post_back(conn, case_id, msg, summary, reply.body if reply else None)
    return summary


def _post_back(conn, case_id: str, msg, summary: dict, reply_body: str | None) -> list[dict]:
    actions = outbound.plan_outbound(msg.platform or "", msg.external_id, summary, reply_body)
    results = outbound.deliver(actions)
    for r in results:
        db.insert(
            conn,
            "outbound_log",
            {
                "id": db.new_id(),
                "case_id": case_id,
                "platform": r.get("platform"),
                "external_id": r.get("external_id"),
                "kind": r.get("kind"),
                "public": bool(r.get("public")),
                "status": r.get("status"),
                "detail": r,
                "created_at": db.now_iso(),
            },
            commit=False,
        )
    if results:
        db.audit(conn, case_id, "ai", "outbound", {"actions": results})
    conn.commit()
    return results
