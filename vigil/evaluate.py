"""Metric computation shared by the eval report and the Streamlit Eval tab.

`load_results_frame` builds the gold-vs-pred frame from persisted cases; `compute_metrics`
turns it into an `EvalMetrics`. Both the report and the UI consume the SAME computation.
"""

from __future__ import annotations

import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, recall_score

from .schemas import DetectorMetrics, EvalMetrics

_RESULTS_SQL = """
SELECT c.message_id      AS id,
       c.is_complaint    AS is_complaint,
       c.clinical_red_flag AS clinical_red_flag,
       c.potential_mdr   AS potential_mdr,
       c.routing_decision AS routing_decision,
       e.gold_is_complaint      AS gold_is_complaint,
       e.gold_clinical_red_flag AS gold_clinical_red_flag,
       e.gold_potential_mdr     AS gold_potential_mdr,
       e.gold_severity   AS gold_severity,
       e.bucket          AS bucket,
       m.raw_text        AS raw_text
FROM cases c
JOIN eval_labels e ON e.message_id = c.message_id
JOIN messages m    ON m.id = c.message_id
ORDER BY c.message_id
"""


def load_results_frame(conn) -> pd.DataFrame:
    rows = conn.execute(_RESULTS_SQL).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def _detector(y_true, y_pred) -> DetectorMetrics:
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", pos_label=1, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist()
    return DetectorMetrics(
        precision=float(p), recall=float(r), f1=float(f), support=int(sum(y_true)), confusion=cm
    )


def _safe_recall(gold, pred) -> float | None:
    gold = gold.astype(int)
    if gold.sum() == 0:
        return None
    return float(recall_score(gold, pred.astype(int), zero_division=0))


def compute_metrics(df: pd.DataFrame) -> EvalMetrics:
    if df.empty:
        raise ValueError("No cases to evaluate. Run `make eval` after seeding.")

    yc, pc = df["gold_clinical_red_flag"].astype(int), df["clinical_red_flag"].astype(int)
    ycomp, pcomp = df["gold_is_complaint"].astype(int), df["is_complaint"].astype(int)

    clinical = _detector(yc, pc)
    complaint = _detector(ycomp, pcomp)

    mdr_mask = df["gold_potential_mdr"].astype(int) == 1
    mdr_support = int(mdr_mask.sum())
    mdr_recall = (
        float(
            recall_score(
                df.loc[mdr_mask, "gold_potential_mdr"].astype(int),
                df.loc[mdr_mask, "potential_mdr"].astype(int),
                zero_division=0,
            )
        )
        if mdr_support
        else 0.0
    )

    fn = df[(yc == 1) & (pc == 0)]
    false_negatives = [
        {"id": row.id, "bucket": row.bucket, "text": row.raw_text} for row in fn.itertuples()
    ]

    clinical_auto_sent = int(((yc == 1) & (df["routing_decision"] == "auto_send")).sum())

    per_bucket: dict[str, dict] = {}
    for bucket, g in df.groupby("bucket"):
        per_bucket[bucket] = {
            "n": int(len(g)),
            "clinical_recall": _safe_recall(g["gold_clinical_red_flag"], g["clinical_red_flag"]),
            "complaint_recall": _safe_recall(g["gold_is_complaint"], g["is_complaint"]),
        }

    return EvalMetrics(
        n=int(len(df)),
        clinical=clinical,
        complaint=complaint,
        mdr_recall=mdr_recall,
        mdr_support=mdr_support,
        clinical_false_negatives=false_negatives,
        clinical_auto_sent=clinical_auto_sent,
        per_bucket=per_bucket,
    )
