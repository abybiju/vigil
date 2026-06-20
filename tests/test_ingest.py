"""PII masking is safety-relevant: real PII must never reach a model or the DB."""

import pytest

from vigil.ingest import hash_ref, ingest_message, mask_pii, resolve_journey_stage


def test_email_masked():
    masked, counts = mask_pii("contact me at sarah.jones@example.com please")
    assert "[EMAIL]" in masked
    assert "@" not in masked
    assert counts["[EMAIL]"] == 1


def test_phone_masked():
    masked, _ = mask_pii("call 555-201-9987 anytime")
    assert "[PHONE]" in masked
    assert "201" not in masked


def test_url_masked():
    masked, _ = mask_pii("see https://smileie.com/help/refunds for details")
    assert "[URL]" in masked
    assert "smileie.com/help" not in masked


def test_order_ref_beats_number():
    # Order/SKU refs must be labelled ORDER_REF, not the generic NUMBER sweep.
    masked, _ = mask_pii("my order SML-48213 never arrived")
    assert "[ORDER_REF]" in masked
    assert "[NUMBER]" not in masked
    assert "48213" not in masked


def test_hash_pound_order():
    masked, _ = mask_pii("order #100245 is late")
    assert "[ORDER_REF]" in masked
    assert "100245" not in masked


def test_long_number_masked():
    masked, _ = mask_pii("member id 9981234 on file")
    assert "[NUMBER]" in masked
    assert "9981234" not in masked


def test_name_best_effort():
    masked, counts = mask_pii("Hi, I'm Sarah, quick question")
    assert "[NAME]" in masked
    assert "Sarah" not in masked
    assert counts.get("[NAME]", 0) >= 1


def test_no_raw_pii_leaks_end_to_end():
    text = "I'm John Doe, order ORD-5567, email john@x.com, phone 555-123-4567"
    masked, _ = mask_pii(text)
    for leak in ["John", "john@x.com", "ORD-5567", "555-123-4567"]:
        assert leak not in masked


def test_resolve_journey_stage_mapping():
    mapping = {"SML-1": "in_treatment"}
    assert resolve_journey_stage("SML-1", mapping) == "in_treatment"
    assert resolve_journey_stage("SML-unknown", mapping) == "unknown"
    assert resolve_journey_stage(None, mapping) == "unknown"
    assert resolve_journey_stage("SML-1", {"SML-1": "bogus_stage"}) == "unknown"


def test_hash_ref_is_stable_and_not_raw():
    h1 = hash_ref("cust-1234")
    h2 = hash_ref("cust-1234")
    assert h1 == h2
    assert h1 is not None and "1234" not in h1
    assert hash_ref(None) is None


def test_ingest_message_masks_and_hashes():
    msg = ingest_message(
        {
            "raw_text": "I'm Sarah, email sarah@x.com, my tooth hurts",
            "customer_ref": "cust-99",
            "order_ref": "SML-1",
            "journey_stage": "in_treatment",
        }
    )
    assert "sarah@x.com" not in msg.raw_text
    assert "[EMAIL]" in msg.raw_text
    assert msg.customer_ref is not None and "cust-99" not in msg.customer_ref
    assert msg.journey_stage == "in_treatment"
    assert msg.id  # auto-generated
