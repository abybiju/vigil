"""Webhook service: payload -> live pipeline -> persisted case, with a mocked LLM (no API)."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from vigil import db
from vigil.webhook import app, get_client_dep, get_conn_dep, get_retriever_dep

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "sample_webhooks"

CLINICAL_TRIAGE = {
    "intent": ["clinical"], "is_complaint": True, "complaint_basis": "safety",
    "severity": "serious", "potential_mdr": True, "mdr_rationale": "loose tooth",
    "extraction": {"patient_narrative": "Patient reports a loose tooth.", "photo_requested": False},
    "confidence": {"complaint": 0.9, "mdr": 0.85},
}
CLINICAL_SAFETY = {"clinical_red_flag": True, "signals": ["loose tooth"], "confidence": 0.97}

NONCLINICAL_TRIAGE = {
    "intent": ["shipping"], "is_complaint": False, "complaint_basis": "none",
    "severity": "none", "potential_mdr": False, "mdr_rationale": "",
    "extraction": {"patient_narrative": "Asks where the impression kit is.", "photo_requested": False},
    "confidence": {"complaint": 0.1, "mdr": 0.0},
}
NONCLINICAL_SAFETY = {"clinical_red_flag": False, "signals": [], "confidence": 0.95}
REPLY = {"body": "Your kit ships in 1-2 business days.", "answerable": True}


def _fake_client(triage, clinical, reply=None):
    def create(**kwargs):
        name = kwargs["tool_choice"]["name"]
        inp = {"record_triage": triage, "clinical_safety": clinical, "draft_reply": reply}[name]
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", id="x", input=inp)], stop_reason="tool_use")
    return SimpleNamespace(messages=SimpleNamespace(create=MagicMock(side_effect=create)))


def _client(tmp_path, fake):
    conn = db.init_db(tmp_path / "wh.db")
    app.dependency_overrides[get_conn_dep] = lambda: conn
    app.dependency_overrides[get_client_dep] = lambda: fake
    app.dependency_overrides[get_retriever_dep] = lambda: None
    return TestClient(app), conn


def _teardown():
    app.dependency_overrides.clear()


def _load(name):
    return json.loads((SAMPLES / name).read_text())


def test_clinical_webhook_is_held_and_pii_masked(tmp_path):
    client, conn = _client(tmp_path, _fake_client(CLINICAL_TRIAGE, CLINICAL_SAFETY))
    try:
        r = client.post("/webhooks/gorgias", json=_load("gorgias.json"))
        assert r.status_code == 200
        body = r.json()
        assert body["routing_decision"] == "vigilance_review"  # MDR candidate
        assert body["held_for_human"] is True
        assert body["reply"] is None  # held lanes never get a draft

        # The persisted message must have masked PII (no name/email from the payload).
        row = conn.execute("SELECT raw_text, customer_ref FROM messages WHERE id = ?", (body["message_id"],)).fetchone()
        assert "Jordan" not in row["raw_text"]
        assert "jordan.lee@example.com" not in (row["raw_text"] or "")
        assert "[ORDER_REF]" in row["raw_text"] or "[NAME]" in row["raw_text"]

        # Outbound (dry-run by default): a held case posts a NOTE back, never a public reply.
        outbound = body["outbound"]
        assert outbound and all(a["status"] == "dry_run" for a in outbound)
        assert [a["kind"] for a in outbound] == ["note"]
        assert all(a["public"] is False for a in outbound)
    finally:
        _teardown()


def test_safe_lane_webhook_gets_a_reply(tmp_path):
    fake = _fake_client(NONCLINICAL_TRIAGE, NONCLINICAL_SAFETY, REPLY)
    client, conn = _client(tmp_path, fake)
    try:
        r = client.post("/webhooks/zendesk", json=_load("zendesk.json"))
        assert r.status_code == 200
        body = r.json()
        assert body["held_for_human"] is False
        assert body["routing_decision"] in ("agent_draft", "auto_send")
        assert body["reply"] and "pending human review" in body["reply"]
    finally:
        _teardown()


def test_unknown_platform_404(tmp_path):
    client, _ = _client(tmp_path, _fake_client(CLINICAL_TRIAGE, CLINICAL_SAFETY))
    try:
        assert client.post("/webhooks/nope", json={"x": 1}).status_code == 404
    finally:
        _teardown()


def test_empty_text_422(tmp_path):
    client, _ = _client(tmp_path, _fake_client(CLINICAL_TRIAGE, CLINICAL_SAFETY))
    try:
        assert client.post("/webhooks/generic", json={"raw_text": "   "}).status_code == 422
    finally:
        _teardown()


def test_healthz():
    assert TestClient(app).get("/healthz").json() == {"status": "ok"}


def test_signed_request_enforced(tmp_path, monkeypatch):
    from vigil.webhook_security import sign_headers

    monkeypatch.setenv("VIGIL_WEBHOOK_SECRET", "secret-123")
    client, _ = _client(tmp_path, _fake_client(CLINICAL_TRIAGE, CLINICAL_SAFETY))
    try:
        body = json.dumps(_load("gorgias.json")).encode()

        # Unsigned request is rejected once a secret is configured.
        unsigned = client.post("/webhooks/gorgias", content=body, headers={"Content-Type": "application/json"})
        assert unsigned.status_code == 401

        # Correctly signed request is accepted and processed.
        headers = {"Content-Type": "application/json", **sign_headers("gorgias", body, "secret-123")}
        signed = client.post("/webhooks/gorgias", content=body, headers=headers)
        assert signed.status_code == 200
        assert signed.json()["held_for_human"] is True
    finally:
        _teardown()
