"""Pipeline wiring + model-cache behaviour, exercised with a fake Anthropic client (no API)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from vigil import db
from vigil.pipeline import process_message
from vigil.schemas import Message

TRIAGE_INPUT = {
    "intent": ["clinical"],
    "is_complaint": True,
    "complaint_basis": "safety",
    "severity": "serious",
    "potential_mdr": True,
    "mdr_rationale": "Reports a loose tooth.",
    "extraction": {"patient_narrative": "Patient reports a loose tooth.", "photo_requested": False},
    "confidence": {"complaint": 0.9, "mdr": 0.85},
}
CLINICAL_INPUT = {"clinical_red_flag": True, "signals": ["loose tooth"], "confidence": 0.95}


def _fake_create(**kwargs):
    name = kwargs["tool_choice"]["name"]
    inp = TRIAGE_INPUT if name == "record_triage" else CLINICAL_INPUT
    block = SimpleNamespace(type="tool_use", id="x", input=inp)
    return SimpleNamespace(content=[block], stop_reason="tool_use")


def _client():
    return SimpleNamespace(messages=SimpleNamespace(create=MagicMock(side_effect=_fake_create)))


def _msg():
    return Message(id="m1", raw_text="one of my bottom teeth feels loose now", journey_stage="in_treatment")


def test_mdr_case_routes_to_vigilance_review():
    # Serious MDR candidate -> vigilance lane (held, never auto-answered).
    client = _client()
    res = process_message(client, _msg(), retriever=None, conn=None)
    assert res.clinical.clinical_red_flag is True
    assert res.triage.is_complaint is True
    assert res.routing.routing_decision == "vigilance_review"


def test_cache_prevents_second_round_of_calls(tmp_path):
    conn = db.init_db(tmp_path / "t.db")
    client = _client()
    msg = _msg()

    process_message(client, msg, conn=conn)
    assert client.messages.create.call_count == 2  # triage + clinical

    # Same masked text -> both calls served from cache, no new API calls.
    res2 = process_message(client, msg, conn=conn)
    assert client.messages.create.call_count == 2
    assert res2.routing.routing_decision == "vigilance_review"

    # no_cache forces fresh calls.
    process_message(client, msg, conn=conn, no_cache=True)
    assert client.messages.create.call_count == 4
