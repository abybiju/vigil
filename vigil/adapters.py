"""Inbound adapters: normalize a support-platform webhook payload into the `raw` dict
that `ingest_message` expects. This is the integration seam — the pipeline downstream
(triage / clinical-safety / router / respond) never changes per platform.

Each adapter is a pure function `(payload: dict) -> raw: dict` with keys:
  source, channel, customer_ref, order_ref, journey_stage?, received_at?, raw_text

PII (emails/names/phones) passed here is masked + hashed inside `ingest_message`, so
adapters may pass raw customer identifiers — nothing unmasked is persisted.
"""

from __future__ import annotations

import re
from typing import Any, Callable

VALID_STAGES = {
    "pre_kit", "post_impression", "preview_approved", "in_treatment", "post_treatment", "unknown",
}


def _first(*vals: Any) -> Any:
    for v in vals:
        if v:
            return v
    return None


def _dig(d: dict, *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _order_ref(payload: dict) -> str | None:
    for key in ("order_ref", "order_number", "order_name", "order_id", "order"):
        v = payload.get(key)
        if v:
            return str(v)
    # also look one level into common containers
    for container in ("ticket", "order", "data"):
        sub = payload.get(container)
        if isinstance(sub, dict):
            r = _order_ref(sub)
            if r:
                return r
    return None


def _stage(payload: dict) -> str | None:
    s = payload.get("journey_stage")
    return s if s in VALID_STAGES else None


def from_gorgias(p: dict) -> dict:
    """Gorgias ticket/message webhook."""
    ticket = p.get("ticket") if isinstance(p.get("ticket"), dict) else p
    msg = p.get("message") if isinstance(p.get("message"), dict) else {}
    customer = _first(ticket.get("customer"), msg.get("sender"), {}) or {}
    channel = _first(ticket.get("channel"), msg.get("channel"), "email")
    text = _first(
        msg.get("stripped_text"), msg.get("body_text"), msg.get("body"),
        ticket.get("stripped_text"), ticket.get("subject"),
    )
    return {
        "source": "chat" if channel in ("chat", "messenger", "sms") else "email",
        "channel": _first(channel, "gorgias"),
        "customer_ref": _first(customer.get("email"), customer.get("id")),
        "order_ref": _order_ref(p),
        "journey_stage": _stage(p),
        "received_at": _first(ticket.get("created_datetime"), msg.get("created_datetime")),
        "raw_text": text,
    }


def from_zendesk(p: dict) -> dict:
    """Zendesk ticket / trigger webhook."""
    ticket = p.get("ticket") if isinstance(p.get("ticket"), dict) else p
    requester = _first(ticket.get("requester"), ticket.get("via", {}).get("source", {}).get("from"), {}) or {}
    channel = _first(_dig(ticket, "via", "channel"), "email")
    # latest_comment when present, else description
    text = _first(
        _dig(ticket, "latest_comment", "body"),
        ticket.get("description"),
        ticket.get("subject"),
    )
    return {
        "source": "chat" if channel in ("chat", "messaging", "sms") else "email",
        "channel": _first(channel, "zendesk"),
        "customer_ref": _first(requester.get("email"), requester.get("address"), requester.get("id")),
        "order_ref": _order_ref(p),
        "journey_stage": _stage(p),
        "received_at": ticket.get("created_at"),
        "raw_text": text,
    }


# Shopify fulfillment status -> our journey vocabulary (best-effort enrichment).
_SHOPIFY_STAGE = {"fulfilled": "in_treatment", "partial": "preview_approved", "unfulfilled": "pre_kit"}


def from_shopify(p: dict) -> dict:
    """Shopify order/customer note payload. Shopify also enriches journey via fulfillment status."""
    customer = p.get("customer") if isinstance(p.get("customer"), dict) else {}
    text = _first(p.get("note"), p.get("message"), _dig(p, "note_attributes", "value"))
    stage = _stage(p) or _SHOPIFY_STAGE.get(p.get("fulfillment_status") or "")
    return {
        "source": "email",
        "channel": "shopify",
        "customer_ref": _first(customer.get("email"), customer.get("id"), p.get("email")),
        "order_ref": _order_ref(p),
        "journey_stage": stage,
        "received_at": p.get("created_at"),
        "raw_text": text,
    }


def from_email(p: dict) -> dict:
    """Generic inbound-email payload (SES / SendGrid Inbound Parse / IMAP poller)."""
    subject = p.get("subject") or ""
    body = _first(p.get("text"), p.get("body"), p.get("plain"), p.get("html"))
    # Prepend the subject so context isn't lost; keep it readable for the model.
    text = f"{subject}\n\n{body}".strip() if subject and body else (body or subject or None)
    sender = p.get("from") or p.get("sender") or p.get("envelope", {}).get("from")
    if isinstance(sender, dict):
        sender = sender.get("email") or sender.get("address")
    return {
        "source": "email",
        "channel": "email",
        "customer_ref": sender,
        "order_ref": _order_ref(p),
        "journey_stage": _stage(p),
        "received_at": p.get("date") or p.get("received_at"),
        "raw_text": text,
    }


def from_generic(p: dict) -> dict:
    """Pass-through for a payload already shaped like the ingest contract."""
    return {
        "source": p.get("source") or "email",
        "channel": p.get("channel") or "api",
        "customer_ref": p.get("customer_ref"),
        "order_ref": _order_ref(p),
        "journey_stage": _stage(p),
        "received_at": p.get("received_at"),
        "raw_text": p.get("raw_text") or p.get("text") or p.get("message"),
    }


ADAPTERS: dict[str, Callable[[dict], dict]] = {
    "gorgias": from_gorgias,
    "zendesk": from_zendesk,
    "shopify": from_shopify,
    "email": from_email,
    "generic": from_generic,
}
