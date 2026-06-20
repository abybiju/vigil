"""Schema contracts: enum validity and confidence range (validators, not ge/le)."""

import pytest
from pydantic import ValidationError

from vigil.schemas import (
    ClinicalSafety,
    Confidence,
    Extraction,
    TriageResult,
)


def _valid_triage(**overrides):
    base = dict(
        intent=["clinical"],
        is_complaint=True,
        complaint_basis="safety",
        severity="serious",
        potential_mdr=True,
        mdr_rationale="Reported tooth mobility.",
        extraction=Extraction(patient_narrative="Patient reports a loose tooth."),
        confidence=Confidence(complaint=0.9, mdr=0.8),
    )
    base.update(overrides)
    return TriageResult(**base)


def test_valid_triage_constructs():
    t = _valid_triage()
    assert t.is_complaint is True
    assert t.extraction.photo_requested is False  # default
    assert t.intent == ["clinical"]


def test_confidence_rejects_out_of_range():
    with pytest.raises(ValidationError):
        Confidence(complaint=1.5, mdr=0.2)
    with pytest.raises(ValidationError):
        Confidence(complaint=-0.1, mdr=0.2)


def test_invalid_enum_rejected():
    with pytest.raises(ValidationError):
        _valid_triage(severity="catastrophic")
    with pytest.raises(ValidationError):
        _valid_triage(complaint_basis="vibes")


def test_clinical_safety_defaults():
    cs = ClinicalSafety(clinical_red_flag=True)
    assert cs.signals == []
    assert cs.confidence == 0.0


def test_extraction_optionals_default_none():
    e = Extraction(patient_narrative="x")
    assert e.device is None
    assert e.body_site is None
    assert e.event_date is None
