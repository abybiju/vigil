"""The routing decision — PURE Python, never the LLM. This is the safety boundary.

Priority order is deliberately safety-first: a clinical red flag or a potential MDR event
can NEVER be auto-answered. The clinical-safety pass is authoritative for the clinical gate.

Routing table (spec §4):
  clinical_red_flag                          -> clinical_review   (never auto-send)
  potential_mdr                              -> vigilance_review  (clinical + quality)
  is_complaint (non-clinical)                -> agent_draft       (log + draft)
  auto-answerable & high retrieval-confidence-> auto_send         (grounded)
  else                                       -> agent_draft
"""

from __future__ import annotations

from . import config
from .rules import is_auto_answerable
from .schemas import ClinicalSafety, RoutingResult, TriageResult

# Decisions that are NOT a human-reviewed lane. A clinical/MDR case must never land here.
NON_GATED_DECISIONS = {"auto_send", "agent_draft"}


def route(
    triage: TriageResult,
    clinical: ClinicalSafety,
    retrieval_confidence: float = 0.0,
    *,
    autosend_threshold: float | None = None,
) -> RoutingResult:
    threshold = config.RETRIEVAL_AUTOSEND_THRESHOLD if autosend_threshold is None else autosend_threshold

    crf = bool(clinical.clinical_red_flag)
    is_complaint = bool(triage.is_complaint)
    potential_mdr = bool(triage.potential_mdr)

    # MDR-candidate first: vigilance_review is the "clinical + quality" superset lane (it includes
    # clinical attention plus reportability assessment), so it takes precedence over a plain clinical
    # flag. Both are human-gated lanes, so a clinical/MDR case is never auto-answered either way.
    if potential_mdr:
        decision = "vigilance_review"
        reason = "Potential MDR-reportable event — routed to clinical + quality vigilance review (human gate; never auto-answered)."
    elif crf:
        decision = "clinical_review"
        reason = "Clinical red flag detected — held for clinical review; a clinical case is never auto-answered."
    elif is_complaint:
        decision = "agent_draft"
        reason = "Non-clinical complaint — logged and routed to an agent to draft a reply."
    elif is_auto_answerable(triage.intent) and retrieval_confidence >= threshold:
        decision = "auto_send"
        reason = f"Deterministic informational request with a grounded answer (retrieval={retrieval_confidence:.2f} ≥ {threshold:.2f})."
    else:
        decision = "agent_draft"
        reason = "No high-confidence grounded answer — routed to an agent."

    return RoutingResult(
        routing_decision=decision,
        reason=reason,
        clinical_red_flag=crf,
        is_complaint=is_complaint,
        potential_mdr=potential_mdr,
    )
