"""Outbound: post Vigil's triage result back to the source ticket/order.

What gets posted is decided by `plan_outbound`, which ENFORCES the human gate:
  - held lanes (clinical_review / vigilance_review) -> an internal triage note + alert tags ONLY.
    Never a public customer reply. A clinical/MDR case is never auto-answered, inbound or outbound.
  - agent_draft -> internal note + the drafted reply as an INTERNAL (agent-review) note + tags.
  - auto_send  -> the grounded reply (public only if explicitly allowed) + tags.

Delivery modes (env `VIGIL_OUTBOUND_MODE`): `dry_run` (default — records intent, no HTTP),
`live` (calls the platform API with configured credentials), `off` (do nothing). Dry-run makes the
whole flow demoable without any real credentials.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from . import config

# Platforms we can actually post back to. Email/generic have no ticket to update.
POSTABLE = {"gorgias", "zendesk", "shopify"}


@dataclass
class OutboundAction:
    platform: str
    external_id: str
    kind: str               # note | reply | tags
    body: str = ""
    tags: list[str] = field(default_factory=list)
    public: bool = False     # True only for an actual public customer reply


def outbound_mode() -> str:
    return (os.environ.get("VIGIL_OUTBOUND_MODE") or "dry_run").strip().lower()


def _allow_autosend_public() -> bool:
    return (os.environ.get("VIGIL_OUTBOUND_ALLOW_AUTOSEND_PUBLIC") or "").strip().lower() in {"1", "true", "yes"}


def _tags(summary: dict) -> list[str]:
    tags = ["vigil:triaged", f"vigil:{summary['routing_decision']}"]
    if summary.get("is_complaint"):
        tags.append("vigil:complaint")
    if summary.get("clinical_red_flag"):
        tags.append("vigil:clinical")
    if summary.get("potential_mdr"):
        tags.append("vigil:mdr-candidate")
    if summary.get("held_for_human"):
        tags.append("vigil:held-for-review")
    return tags


def _note_body(summary: dict) -> str:
    return (
        "🦷 Vigil triage — complaint={is_complaint} · clinical_red_flag={clinical_red_flag} · "
        "potential_mdr={potential_mdr} · severity={severity} → {routing_decision}.\n"
        "{reason}\n"
        "({caption})"
    ).format(caption=config.HUMAN_GATE_CAPTION, **summary)


def plan_outbound(platform: str, external_id: str | None, summary: dict, reply_body: str | None) -> list[OutboundAction]:
    """Decide what to post back. Pure + safety-gated; returns [] when there's nothing/nowhere to post."""
    if not external_id or platform not in POSTABLE:
        return []

    decision = summary["routing_decision"]
    tags = _tags(summary)
    note = OutboundAction(platform, external_id, "note", body=_note_body(summary), tags=tags)

    # Held lanes: alert the humans, never a reply.
    if summary.get("held_for_human"):
        return [note]

    actions = [note]
    if reply_body:
        if decision == "auto_send" and _allow_autosend_public() and not summary.get("clinical_red_flag"):
            actions.append(OutboundAction(platform, external_id, "reply", body=reply_body, public=True))
        else:
            # Drafted reply handed to an agent to review/send — never auto-public by default.
            actions.append(OutboundAction(platform, external_id, "reply", body=reply_body, public=False))
    return actions


# --------------------------------------------------------------------------- #
# Per-platform live senders. Each returns a status dict; missing creds -> skipped.
# --------------------------------------------------------------------------- #
def _env(*names: str) -> str | None:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


def _send_zendesk(action: OutboundAction, http: httpx.Client) -> dict:
    sub = _env("VIGIL_ZENDESK_SUBDOMAIN")
    email = _env("VIGIL_ZENDESK_EMAIL")
    token = _env("VIGIL_ZENDESK_API_TOKEN")
    if not (sub and email and token):
        return {"status": "skipped", "reason": "missing Zendesk credentials"}
    url = f"https://{sub}.zendesk.com/api/v2/tickets/{action.external_id}.json"
    ticket: dict = {"tags": action.tags}
    if action.body:
        ticket["comment"] = {"body": action.body, "public": action.public}
    r = http.put(url, json={"ticket": ticket}, auth=(f"{email}/token", token))
    return {"status": "sent" if r.status_code < 300 else "error", "http_status": r.status_code}


def _send_shopify(action: OutboundAction, http: httpx.Client) -> dict:
    domain = _env("VIGIL_SHOPIFY_DOMAIN")
    token = _env("VIGIL_SHOPIFY_ACCESS_TOKEN")
    if not (domain and token):
        return {"status": "skipped", "reason": "missing Shopify credentials"}
    ver = os.environ.get("VIGIL_SHOPIFY_API_VERSION", "2024-10")
    url = f"https://{domain}/admin/api/{ver}/orders/{action.external_id}.json"
    order = {"id": action.external_id, "tags": ",".join(action.tags)}
    if action.body and action.kind == "note":
        order["note"] = action.body  # Shopify orders have no public reply; note + tags only
    r = http.put(url, json={"order": order}, headers={"X-Shopify-Access-Token": token})
    return {"status": "sent" if r.status_code < 300 else "error", "http_status": r.status_code}


def _send_gorgias(action: OutboundAction, http: httpx.Client) -> dict:
    domain = _env("VIGIL_GORGIAS_DOMAIN")
    email = _env("VIGIL_GORGIAS_EMAIL")
    api_key = _env("VIGIL_GORGIAS_API_KEY")
    if not (domain and email and api_key):
        return {"status": "skipped", "reason": "missing Gorgias credentials"}
    if action.kind == "tags":
        url = f"https://{domain}/api/tickets/{action.external_id}/tags"
        r = http.post(url, json={"tags": [{"name": t} for t in action.tags]}, auth=(email, api_key))
    else:
        url = f"https://{domain}/api/tickets/{action.external_id}/messages"
        source_type = "email" if action.public else "internal-note"
        body = {"via": "api", "source": {"type": source_type}, "from_agent": True, "body_text": action.body}
        r = http.post(url, json=body, auth=(email, api_key))
    return {"status": "sent" if r.status_code < 300 else "error", "http_status": r.status_code}


_SENDERS = {"zendesk": _send_zendesk, "shopify": _send_shopify, "gorgias": _send_gorgias}


def deliver(actions: list[OutboundAction], *, mode: str | None = None, http: httpx.Client | None = None) -> list[dict]:
    """Execute (or simulate) the planned actions. Returns a status record per action."""
    mode = mode or outbound_mode()
    if mode == "off" or not actions:
        return []

    results: list[dict] = []
    own_http = http is None and mode == "live"
    client = http or (httpx.Client(timeout=config.REQUEST_TIMEOUT) if mode == "live" else None)
    try:
        for a in actions:
            base = {"platform": a.platform, "external_id": a.external_id, "kind": a.kind, "public": a.public}
            if mode == "dry_run":
                preview = a.body[:140] if a.body else ", ".join(a.tags)
                results.append({**base, "status": "dry_run", "preview": preview, "tags": a.tags})
            else:  # live
                sender = _SENDERS.get(a.platform)
                if sender is None:
                    results.append({**base, "status": "skipped", "reason": "no sender for platform"})
                else:
                    results.append({**base, **sender(a, client)})
    finally:
        if own_http and client is not None:
            client.close()
    return results
