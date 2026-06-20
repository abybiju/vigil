"""The router is the safety boundary. This exhausts the truth table and asserts the invariant:
a clinical red flag or potential MDR event is NEVER routed to a non-gated lane."""

import itertools

import pytest

from vigil.router import NON_GATED_DECISIONS, route
from vigil.schemas import ClinicalSafety, Confidence, Extraction, TriageResult

THRESHOLD = 0.30
HIGH, LOW = 0.9, 0.0


def make_triage(is_complaint, potential_mdr, auto_intent):
    intent = ["shipping"] if auto_intent else ["other"]
    return TriageResult(
        intent=intent,
        is_complaint=is_complaint,
        complaint_basis="safety" if is_complaint else "none",
        severity="serious" if potential_mdr else "none",
        potential_mdr=potential_mdr,
        mdr_rationale="",
        extraction=Extraction(patient_narrative="x"),
        confidence=Confidence(complaint=0.5, mdr=0.5),
    )


def expected(crf, is_complaint, potential_mdr, auto, retr):
    # MDR-candidate takes precedence over a plain clinical flag (vigilance_review is the superset lane).
    if potential_mdr:
        return "vigilance_review"
    if crf:
        return "clinical_review"
    if is_complaint:
        return "agent_draft"
    if auto and retr >= THRESHOLD:
        return "auto_send"
    return "agent_draft"


@pytest.mark.parametrize(
    "crf,is_complaint,potential_mdr,auto,retr",
    list(itertools.product([True, False], [True, False], [True, False], [True, False], [HIGH, LOW])),
)
def test_truth_table(crf, is_complaint, potential_mdr, auto, retr):
    triage = make_triage(is_complaint, potential_mdr, auto)
    clinical = ClinicalSafety(clinical_red_flag=crf, confidence=0.8)
    result = route(triage, clinical, retr)
    assert result.routing_decision == expected(crf, is_complaint, potential_mdr, auto, retr)


@pytest.mark.parametrize(
    "crf,is_complaint,potential_mdr,auto,retr",
    list(itertools.product([True, False], [True, False], [True, False], [True, False], [HIGH, LOW])),
)
def test_safety_invariant_never_auto_answers_clinical_or_mdr(crf, is_complaint, potential_mdr, auto, retr):
    triage = make_triage(is_complaint, potential_mdr, auto)
    clinical = ClinicalSafety(clinical_red_flag=crf, confidence=0.8)
    result = route(triage, clinical, retr)
    # The core safety invariant: a clinical red flag OR an MDR candidate is never auto-answered.
    if crf or potential_mdr:
        assert result.routing_decision not in NON_GATED_DECISIONS
    # MDR candidate -> vigilance lane; a plain clinical flag (no MDR) -> clinical lane.
    if potential_mdr:
        assert result.routing_decision == "vigilance_review"
    elif crf:
        assert result.routing_decision == "clinical_review"


def test_clinical_overrides_everything():
    # Even a clean non-complaint informational request, if the clinical pass flags it, is held.
    triage = make_triage(is_complaint=False, potential_mdr=False, auto_intent=True)
    clinical = ClinicalSafety(clinical_red_flag=True, confidence=0.6)
    assert route(triage, clinical, HIGH).routing_decision == "clinical_review"
