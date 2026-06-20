"""Compose the full triage pipeline for one message: triage + clinical-safety + deterministic route.

Reused by the eval harness and the UI processing step. Model calls are cached in `model_cache`
(keyed by masked text + model + prompt/schema version) so re-runs are free; pass `no_cache=True`
to force fresh calls.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable

import anthropic

from . import config, db
from .clinical_safety import assess_clinical_safety
from .retrieve import RetrievedChunk, Retriever
from .router import route
from .schemas import ClinicalSafety, MdrDraft, Message, RoutingResult, TriageResult
from .triage import triage_message


@dataclass
class PipelineResult:
    message: Message
    triage: TriageResult
    clinical: ClinicalSafety
    routing: RoutingResult
    retrieval_confidence: float
    top_chunk: RetrievedChunk | None


def _cache_key(kind: str, model: str, text: str) -> str:
    blob = f"{kind}|{model}|{config.PROMPT_VERSION}|{config.SCHEMA_VERSION}|{text}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cached(conn, kind: str, model: str, text: str, schema_model, fn: Callable, no_cache: bool):
    key = _cache_key(kind, model, text)
    if conn is not None and not no_cache:
        row = db.query_one(conn, "SELECT response_json FROM model_cache WHERE cache_key = ?", (key,))
        if row is not None:
            return schema_model.model_validate_json(row["response_json"])
    obj = fn()
    if conn is not None:
        conn.execute(
            "INSERT OR REPLACE INTO model_cache (cache_key, kind, response_json, created_at) VALUES (?, ?, ?, ?)",
            (key, kind, obj.model_dump_json(), db.now_iso()),
        )
        conn.commit()
    return obj


def process_message(
    client: anthropic.Anthropic,
    message: Message,
    *,
    retriever: Retriever | None = None,
    conn=None,
    no_cache: bool = False,
) -> PipelineResult:
    text = message.raw_text

    triage = _cached(
        conn, "triage", config.TRIAGE_MODEL, text, TriageResult,
        lambda: triage_message(client, text, journey_stage=message.journey_stage),
        no_cache,
    )
    clinical = _cached(
        conn, "clinical_safety", config.CLINICAL_MODEL, text, ClinicalSafety,
        lambda: assess_clinical_safety(client, text),
        no_cache,
    )

    top_chunk: RetrievedChunk | None = None
    confidence = 0.0
    if retriever is not None:
        hits = retriever.search(text, k=1)
        if hits:
            top_chunk = hits[0]
            confidence = hits[0].score

    routing = route(triage, clinical, confidence)
    return PipelineResult(
        message=message,
        triage=triage,
        clinical=clinical,
        routing=routing,
        retrieval_confidence=confidence,
        top_chunk=top_chunk,
    )


def build_mdr_draft(triage: TriageResult) -> MdrDraft:
    """Deterministic 3500A-style draft from the extraction (a human reviews before anything leaves)."""
    ex = triage.extraction
    event_type = "injury" if ex.alleged_harm else "malfunction"
    device_problem = ex.issue_type or (ex.device or "device") + " issue — see narrative"
    patient_problem = ex.alleged_harm or ex.body_site or "see narrative"
    narrative = (
        f"{ex.patient_narrative} "
        f"[Triage rationale: {triage.mdr_rationale}] "
        f"({config.HUMAN_GATE_CAPTION})"
    )
    return MdrDraft(
        event_type=event_type,
        device_problem=device_problem,
        patient_problem=patient_problem,
        narrative=narrative,
    )


def persist_case(conn, res: PipelineResult) -> str:
    """Persist a triage result as cases (+ complaint_record + mdr_draft) and audit it. Returns case_id."""
    t, c, rt = res.triage, res.clinical, res.routing
    case_id = db.new_id()
    db.insert(
        conn,
        "cases",
        {
            "id": case_id,
            "message_id": res.message.id,
            "intent_category": list(t.intent),
            "is_complaint": t.is_complaint,
            "complaint_basis": t.complaint_basis,
            "clinical_red_flag": c.clinical_red_flag,
            "severity": t.severity,
            "potential_mdr": t.potential_mdr,
            "mdr_rationale": t.mdr_rationale,
            "conf_complaint": t.confidence.complaint,
            "conf_clinical": c.confidence,
            "conf_mdr": t.confidence.mdr,
            "routing_decision": rt.routing_decision,
            "routing_reason": rt.reason,
            "status": "open",
            "model_version": config.TRIAGE_MODEL,
            "prompt_version": config.PROMPT_VERSION,
            "created_at": db.now_iso(),
        },
        commit=False,
    )

    if t.is_complaint:
        cr_id = db.new_id()
        ex = t.extraction
        db.insert(
            conn,
            "complaint_records",
            {
                "id": cr_id,
                "case_id": case_id,
                "device": ex.device,
                "issue_type": ex.issue_type,
                "onset": ex.onset,
                "duration": ex.duration,
                "alleged_harm": ex.alleged_harm,
                "body_site": ex.body_site,
                "patient_narrative": ex.patient_narrative,
                "event_date": ex.event_date,
                "aligner_step": ex.aligner_step,
                "photo_requested": ex.photo_requested,
            },
            commit=False,
        )
        if t.potential_mdr:
            draft = build_mdr_draft(t)
            db.insert(
                conn,
                "mdr_drafts",
                {
                    "id": db.new_id(),
                    "complaint_record_id": cr_id,
                    "event_type": draft.event_type,
                    "device_problem": draft.device_problem,
                    "patient_problem": draft.patient_problem,
                    "narrative": draft.narrative,
                    "draft_status": draft.draft_status,
                },
                commit=False,
            )

    db.audit(
        conn,
        case_id,
        "ai",
        "triaged",
        {"routing": rt.routing_decision, "clinical_red_flag": c.clinical_red_flag, "potential_mdr": t.potential_mdr},
    )
    conn.commit()
    return case_id
