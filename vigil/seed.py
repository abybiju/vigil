"""Seed the local SQLite DB: schema -> FAQ corpus embeddings -> labelled dataset.

Idempotent: clears seeded/derived tables and reloads. The model_cache is preserved so
eval re-runs stay free. Corpus embedding and dataset loading are guarded so this script
works at every phase (skips gracefully when a piece doesn't exist yet).
"""

from __future__ import annotations

import csv
from pathlib import Path

from . import config, db
from .ingest import ingest_message

CORPUS_DIR = config.ROOT / "data" / "corpus"
DATASET = config.ROOT / "eval" / "dataset.csv"

# Cleared on every seed, in FK-safe order. model_cache is intentionally NOT cleared.
_RESET_TABLES = [
    "audit_log",
    "replies",
    "mdr_drafts",
    "complaint_records",
    "cases",
    "eval_labels",
    "messages",
    "faq_chunks",
]


def _to_bool(v: str | None) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "t", "y"}


def reset_data(conn) -> None:
    for table in _RESET_TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def seed_corpus(conn) -> int:
    files = sorted(CORPUS_DIR.glob("*.json")) if CORPUS_DIR.exists() else []
    if not files:
        return 0
    try:
        from .retrieve import build_corpus  # available from Phase 2 onward
    except ImportError:
        return 0
    return build_corpus(conn, files)


def seed_dataset(conn) -> int:
    if not DATASET.exists():
        return 0
    n = 0
    with DATASET.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            msg = ingest_message(
                {
                    "id": row.get("id") or None,
                    "raw_text": row["text"],
                    "source": row.get("source") or "email",
                    "journey_stage": row.get("journey_stage") or None,
                    "order_ref": row.get("order_ref") or None,
                    "customer_ref": row.get("customer_ref") or None,
                }
            )
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
                    "raw_text": msg.raw_text,
                },
                commit=False,
            )
            db.insert(
                conn,
                "eval_labels",
                {
                    "message_id": msg.id,
                    "gold_is_complaint": _to_bool(row.get("gold_is_complaint")),
                    "gold_clinical_red_flag": _to_bool(row.get("gold_clinical_red_flag")),
                    "gold_potential_mdr": _to_bool(row.get("gold_potential_mdr")),
                    "gold_severity": row.get("gold_severity") or "none",
                    "bucket": row.get("bucket") or "",
                    "notes": row.get("notes") or "",
                },
                commit=False,
            )
            n += 1
    conn.commit()
    return n


def main() -> None:
    conn = db.init_db()
    reset_data(conn)
    n_chunks = seed_corpus(conn)
    n_msgs = seed_dataset(conn)
    print(f"Seeded DB at {config.DB_PATH}")
    print(f"  FAQ chunks embedded: {n_chunks}")
    print(f"  Messages loaded:     {n_msgs}")
    if n_chunks == 0:
        print("  (no corpus yet — add data/corpus/*.json, Phase 2)")
    if n_msgs == 0:
        print("  (no dataset yet — add eval/dataset.csv, Phase 4)")


if __name__ == "__main__":
    main()
