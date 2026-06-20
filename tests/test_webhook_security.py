"""HMAC verification: valid signatures pass, tampering/wrong-secret fails, dev-mode + fail-closed."""

import json

import pytest

from vigil.webhook_security import sign_headers, verify_signature

BODY = json.dumps({"hello": "world"}).encode()
SECRET = "shh-super-secret"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("VIGIL_WEBHOOK_SECRET") or k == "VIGIL_WEBHOOK_REQUIRE_SIGNATURE":
            monkeypatch.delenv(k, raising=False)


def test_no_secret_dev_mode_skips(monkeypatch):
    ok, reason = verify_signature("gorgias", BODY, {})
    assert ok is True
    assert "dev mode" in reason


def test_no_secret_fail_closed(monkeypatch):
    monkeypatch.setenv("VIGIL_WEBHOOK_REQUIRE_SIGNATURE", "true")
    ok, reason = verify_signature("gorgias", BODY, {})
    assert ok is False


@pytest.mark.parametrize("platform", ["gorgias", "email", "generic", "shopify", "zendesk"])
def test_valid_signature_passes(monkeypatch, platform):
    monkeypatch.setenv("VIGIL_WEBHOOK_SECRET", SECRET)
    headers = sign_headers(platform, BODY, SECRET)
    ok, reason = verify_signature(platform, BODY, headers)
    assert ok is True, reason


@pytest.mark.parametrize("platform", ["gorgias", "shopify", "zendesk"])
def test_tampered_body_fails(monkeypatch, platform):
    monkeypatch.setenv("VIGIL_WEBHOOK_SECRET", SECRET)
    headers = sign_headers(platform, BODY, SECRET)
    ok, _ = verify_signature(platform, BODY + b"x", headers)  # body changed after signing
    assert ok is False


def test_wrong_secret_fails(monkeypatch):
    monkeypatch.setenv("VIGIL_WEBHOOK_SECRET", SECRET)
    headers = sign_headers("shopify", BODY, "a-different-secret")
    ok, _ = verify_signature("shopify", BODY, headers)
    assert ok is False


def test_missing_signature_header_fails(monkeypatch):
    monkeypatch.setenv("VIGIL_WEBHOOK_SECRET", SECRET)
    ok, _ = verify_signature("shopify", BODY, {})  # secret set, but no header sent
    assert ok is False


def test_per_platform_secret_overrides_fallback(monkeypatch):
    monkeypatch.setenv("VIGIL_WEBHOOK_SECRET", "fallback")
    monkeypatch.setenv("VIGIL_WEBHOOK_SECRET_SHOPIFY", SECRET)
    headers = sign_headers("shopify", BODY, SECRET)  # signed with the platform-specific secret
    ok, _ = verify_signature("shopify", BODY, headers)
    assert ok is True
