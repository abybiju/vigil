"""Deterministic policy rules — exhaustive over journey stages and intent gating."""

import pytest

from vigil.rules import is_auto_answerable, journey_label, refund_eligibility


@pytest.mark.parametrize(
    "stage,tier,eligible",
    [
        ("pre_kit", "full", True),
        ("post_impression", "full", True),
        ("preview_approved", "partial", True),
        ("in_treatment", "none", False),
        ("post_treatment", "none", False),
        ("unknown", "none", False),
    ],
)
def test_refund_eligibility(stage, tier, eligible):
    d = refund_eligibility(stage)
    assert d.tier == tier
    assert d.eligible is eligible


def test_unknown_defers_to_agent():
    d = refund_eligibility("unknown")
    assert d.needs_agent is True


def test_bogus_stage_falls_back_to_unknown():
    d = refund_eligibility("not_a_stage")
    assert d.tier == "none"
    assert d.needs_agent is True


def test_journey_label_present_for_all_stages():
    for stage in ["pre_kit", "post_impression", "preview_approved", "in_treatment", "post_treatment", "unknown"]:
        assert journey_label(stage)


def test_auto_answerable():
    assert is_auto_answerable(["shipping"]) is True
    assert is_auto_answerable(["payment_refund", "other"]) is True
    assert is_auto_answerable(["impression_kit"]) is True
    # clinical always blocks an auto answer
    assert is_auto_answerable(["shipping", "clinical"]) is False
    assert is_auto_answerable(["clinical"]) is False
    # a vague 'other' alone is not auto-answerable
    assert is_auto_answerable(["other"]) is False
