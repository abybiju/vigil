"""Ingest: mask PII, resolve journey stage, and produce a validated Message.

Masking is deliberately regex-only (no heavy NER) so the project stays clone-and-run.
Names are best-effort — documented honestly in the README. The hard guarantee that
matters is that emails, phones, order/SKU refs, URLs, and long digit runs never reach
a model or the DB. Order is significant: structured tokens (email/url/order) are masked
*before* the generic long-digit-run sweep so they get the most specific label.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from .schemas import JourneyStage, Message

# Substitutions applied in order. Each maps a regex to a typed placeholder.
_SUBSTITUTIONS: list[tuple[str, re.Pattern]] = [
    ("[EMAIL]", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("[URL]", re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)),
    # Order / SKU refs like SML-12345, ORD#1234, "order 100245", INV-9981.
    ("[ORDER_REF]", re.compile(r"\b(?:SML|ORD|SM|INV|ORDER)[-#:\s]?\d{3,}\b", re.IGNORECASE)),
    ("[ORDER_REF]", re.compile(r"#\d{4,}\b")),
    # Phone numbers (NANP-ish, with optional country code and separators).
    ("[PHONE]", re.compile(r"(?:\+?\d{1,2}[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b")),
    # Generic long digit runs (card-ish / ID-ish). Runs AFTER the specific patterns.
    ("[NUMBER]", re.compile(r"\b\d{6,}\b")),
]

# Best-effort name capture. Trigger phrases, capitalised name in group 1.
_NAME_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:[Ii] am|[Ii]'m|[Mm]y name is|[Tt]his is|[Nn]ame:)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)"),
    re.compile(
        r"(?:[Tt]hanks|[Tt]hank you|[Rr]egards|[Ss]incerely|[Bb]est|[Cc]heers)[,!.\s]+"
        r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)"
    ),
]


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    """Return (masked_text, counts_by_placeholder). Pure and deterministic."""
    counts: dict[str, int] = {}
    masked = text

    for placeholder, pattern in _SUBSTITUTIONS:
        masked, n = pattern.subn(placeholder, masked)
        if n:
            counts[placeholder] = counts.get(placeholder, 0) + n

    # Names: replace only the captured group so surrounding words are untouched.
    def _repl(m: re.Match) -> str:
        counts["[NAME]"] = counts.get("[NAME]", 0) + 1
        whole, base = m.group(0), m.start(0)
        return whole[: m.start(1) - base] + "[NAME]" + whole[m.end(1) - base :]

    for pattern in _NAME_PATTERNS:
        masked = pattern.sub(_repl, masked)

    return masked, counts


def hash_ref(value: str | None, *, length: int = 12) -> str | None:
    """Stable short hash for a customer/order ref so we never store the raw identifier."""
    if not value:
        return None
    return "ref_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def resolve_journey_stage(order_ref: str | None, mapping: dict[str, str] | None = None) -> JourneyStage:
    """Resolve journey stage from an order ref via a rules table (deterministic).

    In a real deployment this joins against the order system. For the MVP we accept an
    optional mapping (e.g. seeded fixtures); unknown / missing refs resolve to 'unknown'.
    """
    if order_ref and mapping and order_ref in mapping:
        stage = mapping[order_ref]
        valid = {"pre_kit", "post_impression", "preview_approved", "in_treatment", "post_treatment", "unknown"}
        return stage if stage in valid else "unknown"  # type: ignore[return-value]
    return "unknown"


def ingest_message(raw: dict, *, stage_mapping: dict[str, str] | None = None) -> Message:
    """Load a raw inbound dict -> mask PII -> resolve stage -> validated Message.

    `raw` keys: id?, source?, channel?, received_at?, customer_ref?, order_ref?,
    journey_stage?, raw_text (required).
    """
    from .db import new_id  # local import avoids a cycle

    masked_text, _ = mask_pii(raw["raw_text"])

    journey = raw.get("journey_stage") or resolve_journey_stage(raw.get("order_ref"), stage_mapping)

    received = raw.get("received_at")
    if received is None:
        received = datetime.now(timezone.utc)

    return Message(
        id=raw.get("id") or new_id(),
        source=raw.get("source", "email"),
        channel=raw.get("channel"),
        received_at=received,
        customer_ref=hash_ref(raw.get("customer_ref")),
        order_ref=raw.get("order_ref"),
        journey_stage=journey,
        raw_text=masked_text,
        platform=raw.get("platform"),
        external_id=(str(raw["external_id"]) if raw.get("external_id") is not None else None),
    )
