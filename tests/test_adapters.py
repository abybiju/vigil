"""Adapters normalize each platform's payload into the ingest contract."""

import json
from pathlib import Path

import pytest

from vigil.adapters import ADAPTERS, from_email, from_gorgias, from_shopify, from_zendesk

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "sample_webhooks"


def _load(name):
    return json.loads((SAMPLES / name).read_text())


def test_gorgias_maps_text_customer_order():
    raw = from_gorgias(_load("gorgias.json"))
    # Adapter prefers the message body over the subject line.
    assert "feels loose" in raw["raw_text"]
    assert raw["customer_ref"] == "jordan.lee@example.com"
    assert raw["channel"] == "email"
    assert raw["source"] == "email"


def test_zendesk_uses_description_and_requester():
    raw = from_zendesk(_load("zendesk.json"))
    assert "impression kit" in raw["raw_text"]
    assert raw["customer_ref"] == "sam.taylor@example.com"
    assert raw["channel"] == "email"


def test_shopify_maps_note_order_and_enriches_journey():
    raw = from_shopify(_load("shopify.json"))
    assert "crack in one of the trays" in raw["raw_text"]
    assert raw["order_ref"] == "1234"
    assert raw["customer_ref"] == "alex.morgan@example.com"
    assert raw["journey_stage"] == "in_treatment"  # fulfillment_status=fulfilled
    assert raw["channel"] == "shopify"


def test_email_prepends_subject_and_extracts_sender():
    raw = from_email(_load("email.json"))
    assert "gum bleeding" in raw["raw_text"]
    assert raw["raw_text"].startswith("billing + something else")  # subject prepended
    assert raw["customer_ref"] == "casey.rivera@example.com"
    assert raw["channel"] == "email"


@pytest.mark.parametrize("name", ["gorgias", "zendesk", "shopify", "email"])
def test_every_adapter_yields_nonempty_text(name):
    raw = ADAPTERS[name](_load(f"{name}.json"))
    assert raw["raw_text"] and raw["raw_text"].strip()


def test_unknown_fields_tolerated():
    # Adapters must not crash on a sparse payload.
    assert from_gorgias({"message": {"body_text": "hi"}})["raw_text"] == "hi"
    assert from_zendesk({"ticket": {"description": "hi"}})["raw_text"] == "hi"
    assert from_email({"text": "hi"})["raw_text"] == "hi"
