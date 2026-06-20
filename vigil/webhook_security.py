"""HMAC signature verification for inbound webhooks.

Each platform signs its payload with a shared secret; Vigil recomputes the HMAC over the
RAW request body and compares in constant time. Real per-platform schemes:

  Shopify  : header `X-Shopify-Hmac-Sha256` = base64(HMAC-SHA256(body, secret))
  Zendesk  : header `X-Zendesk-Webhook-Signature` = base64(HMAC-SHA256(timestamp + body, secret)),
             with `X-Zendesk-Webhook-Signature-Timestamp`
  generic  : header `X-Vigil-Signature` = "sha256=" + hex(HMAC-SHA256(body, secret))
             (used for gorgias/email/generic; Gorgias' own scheme is custom — configure to taste)

Secrets come from env: `VIGIL_WEBHOOK_SECRET_<PLATFORM>` (e.g. VIGIL_WEBHOOK_SECRET_SHOPIFY),
falling back to `VIGIL_WEBHOOK_SECRET`. Posture:
  - a secret IS configured for the platform  -> signature is REQUIRED and enforced.
  - no secret configured                      -> skipped (dev/demo), unless
    `VIGIL_WEBHOOK_REQUIRE_SIGNATURE=true` forces fail-closed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Mapping

GENERIC_HEADER = "x-vigil-signature"
SHOPIFY_HEADER = "x-shopify-hmac-sha256"
ZENDESK_SIG_HEADER = "x-zendesk-webhook-signature"
ZENDESK_TS_HEADER = "x-zendesk-webhook-signature-timestamp"


def secret_for(platform: str) -> str | None:
    return os.environ.get(f"VIGIL_WEBHOOK_SECRET_{platform.upper()}") or os.environ.get(
        "VIGIL_WEBHOOK_SECRET"
    )


def _require_signature() -> bool:
    return os.environ.get("VIGIL_WEBHOOK_REQUIRE_SIGNATURE", "").strip().lower() in {"1", "true", "yes"}


def _digest(body: bytes, secret: str) -> hmac.HMAC:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256)


def _hex(body: bytes, secret: str) -> str:
    return _digest(body, secret).hexdigest()


def _b64(body: bytes, secret: str) -> str:
    return base64.b64encode(_digest(body, secret).digest()).decode("ascii")


def _verify_generic(body: bytes, secret: str, h: Mapping[str, str]) -> bool:
    got = h.get(GENERIC_HEADER, "")
    if got.startswith("sha256="):
        got = got.split("=", 1)[1]
    return hmac.compare_digest(got, _hex(body, secret))


def _verify_shopify(body: bytes, secret: str, h: Mapping[str, str]) -> bool:
    return hmac.compare_digest(h.get(SHOPIFY_HEADER, ""), _b64(body, secret))


def _verify_zendesk(body: bytes, secret: str, h: Mapping[str, str]) -> bool:
    ts = h.get(ZENDESK_TS_HEADER, "")
    expected = base64.b64encode(_digest(ts.encode("utf-8") + body, secret).digest()).decode("ascii")
    return hmac.compare_digest(h.get(ZENDESK_SIG_HEADER, ""), expected)


_VERIFIERS = {"shopify": _verify_shopify, "zendesk": _verify_zendesk}


def verify_signature(platform: str, body: bytes, headers: Mapping[str, str]) -> tuple[bool, str]:
    """Return (ok, reason). `headers` may be any case-insensitively iterable mapping."""
    secret = secret_for(platform)
    if not secret:
        if _require_signature():
            return False, "no signing secret configured (fail-closed)"
        return True, "unsigned (dev mode — no secret configured)"

    h = {k.lower(): v for k, v in headers.items()}
    verifier = _VERIFIERS.get(platform, _verify_generic)
    scheme = platform if platform in _VERIFIERS else "generic"
    ok = verifier(body, secret, h)
    return ok, f"{scheme} signature {'ok' if ok else 'mismatch'}"


def sign_headers(platform: str, body: bytes, secret: str, *, timestamp: str | None = None) -> dict[str, str]:
    """Produce the signature header(s) a sender would attach — used by tests, docs, and clients."""
    if platform == "shopify":
        return {"X-Shopify-Hmac-Sha256": _b64(body, secret)}
    if platform == "zendesk":
        ts = timestamp or "2026-06-20T15:00:00Z"
        sig = base64.b64encode(_digest(ts.encode("utf-8") + body, secret).digest()).decode("ascii")
        return {"X-Zendesk-Webhook-Signature": sig, "X-Zendesk-Webhook-Signature-Timestamp": ts}
    return {"X-Vigil-Signature": "sha256=" + _hex(body, secret)}
