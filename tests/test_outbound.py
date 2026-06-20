"""Outbound: the human-gate-enforcing planner, dry-run, and live delivery (mocked HTTP)."""

import pytest

from vigil.outbound import OutboundAction, deliver, plan_outbound


def _summary(routing, *, complaint=True, clinical=False, mdr=False, severity="none", held=False):
    return {
        "routing_decision": routing, "is_complaint": complaint, "clinical_red_flag": clinical,
        "potential_mdr": mdr, "severity": severity, "held_for_human": held,
        "reason": "because reasons",
    }


# ---- planner safety ----
def test_held_clinical_posts_note_only_never_reply():
    s = _summary("clinical_review", clinical=True, severity="serious", held=True)
    actions = plan_outbound("gorgias", "123", s, reply_body="should NOT be sent")
    assert [a.kind for a in actions] == ["note"]
    assert all(not a.public for a in actions)
    assert all(a.kind != "reply" for a in actions)


def test_held_mdr_posts_note_only():
    s = _summary("vigilance_review", clinical=True, mdr=True, severity="serious", held=True)
    actions = plan_outbound("zendesk", "55", s, reply_body="nope")
    assert [a.kind for a in actions] == ["note"]
    assert "vigil:mdr-candidate" in actions[0].tags


def test_agent_draft_reply_is_internal_not_public():
    s = _summary("agent_draft", complaint=True)
    actions = plan_outbound("zendesk", "55", s, reply_body="here is a draft")
    kinds = [a.kind for a in actions]
    assert "note" in kinds and "reply" in kinds
    reply = next(a for a in actions if a.kind == "reply")
    assert reply.public is False  # agent reviews before sending


def test_autosend_public_only_when_allowed(monkeypatch):
    s = _summary("auto_send", complaint=False)
    # default: not public
    assert all(not a.public for a in plan_outbound("zendesk", "55", s, "grounded reply"))
    # opt-in -> public
    monkeypatch.setenv("VIGIL_OUTBOUND_ALLOW_AUTOSEND_PUBLIC", "true")
    actions = plan_outbound("zendesk", "55", s, "grounded reply")
    assert any(a.kind == "reply" and a.public for a in actions)


def test_autosend_never_public_if_clinical(monkeypatch):
    monkeypatch.setenv("VIGIL_OUTBOUND_ALLOW_AUTOSEND_PUBLIC", "true")
    s = _summary("auto_send", clinical=True)  # defensive: clinical can't go public even on auto_send
    assert all(not a.public for a in plan_outbound("zendesk", "55", s, "x"))


def test_no_external_id_or_unpostable_platform_yields_nothing():
    assert plan_outbound("zendesk", None, _summary("agent_draft"), "x") == []
    assert plan_outbound("email", "msg-1", _summary("agent_draft"), "x") == []  # email has no ticket


# ---- delivery ----
class _Resp:
    def __init__(self, status=200):
        self.status_code = status


class _Http:
    def __init__(self):
        self.calls = []

    def put(self, url, **kw):
        self.calls.append(("PUT", url, kw))
        return _Resp(200)

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return _Resp(200)


def test_dry_run_records_without_http():
    http = _Http()
    out = deliver([OutboundAction("zendesk", "55", "note", body="hi", tags=["vigil:triaged"])], mode="dry_run", http=http)
    assert out[0]["status"] == "dry_run"
    assert http.calls == []  # no network in dry-run


def test_off_mode_does_nothing():
    assert deliver([OutboundAction("zendesk", "55", "note", body="hi")], mode="off") == []


def test_live_zendesk_calls_api(monkeypatch):
    monkeypatch.setenv("VIGIL_ZENDESK_SUBDOMAIN", "smileie")
    monkeypatch.setenv("VIGIL_ZENDESK_EMAIL", "agent@smileie.com")
    monkeypatch.setenv("VIGIL_ZENDESK_API_TOKEN", "tok")
    http = _Http()
    action = OutboundAction("zendesk", "55", "note", body="triage note", tags=["vigil:triaged", "vigil:clinical"])
    out = deliver([action], mode="live", http=http)

    assert out[0]["status"] == "sent"
    method, url, kw = http.calls[0]
    assert method == "PUT"
    assert url == "https://smileie.zendesk.com/api/v2/tickets/55.json"
    assert kw["json"]["ticket"]["comment"] == {"body": "triage note", "public": False}
    assert kw["json"]["ticket"]["tags"] == ["vigil:triaged", "vigil:clinical"]
    assert kw["auth"] == ("agent@smileie.com/token", "tok")


def test_live_missing_credentials_is_skipped(monkeypatch):
    for k in ("VIGIL_SHOPIFY_DOMAIN", "VIGIL_SHOPIFY_ACCESS_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    out = deliver([OutboundAction("shopify", "9", "note", body="x")], mode="live", http=_Http())
    assert out[0]["status"] == "skipped"
