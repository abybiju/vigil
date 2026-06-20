"""structured_call: schema cleaning for strict mode + the validate/retry loop (mocked client)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from vigil.llm import schema_for, structured_call
from vigil.schemas import ClinicalSafety, TriageResult


def _walk_assert_strict_valid(node):
    if isinstance(node, dict):
        assert "$ref" not in node, "refs must be inlined"
        assert "$defs" not in node, "defs must be inlined away"
        for bad in ["minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "pattern", "format"]:
            assert bad not in node, f"unsupported keyword {bad} leaked into strict schema"
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
        for v in node.values():
            _walk_assert_strict_valid(v)
    elif isinstance(node, list):
        for x in node:
            _walk_assert_strict_valid(x)


@pytest.mark.parametrize("model", [TriageResult, ClinicalSafety])
def test_schema_for_is_strict_valid(model):
    _walk_assert_strict_valid(schema_for(model))


def _resp(input_dict, block_id="b"):
    block = SimpleNamespace(type="tool_use", id=block_id, input=input_dict)
    return SimpleNamespace(content=[block], stop_reason="tool_use")


def test_retry_on_validation_error_then_succeeds():
    invalid = _resp({"clinical_red_flag": "definitely-not-a-bool"}, "a")
    valid = _resp({"clinical_red_flag": True, "signals": ["loose tooth"], "confidence": 0.9}, "b")
    client = SimpleNamespace(messages=SimpleNamespace(create=MagicMock(side_effect=[invalid, valid])))

    out = structured_call(
        client, model="m", system="s", user="u",
        schema_model=ClinicalSafety, tool_name="clinical_safety", max_retries=1,
    )
    assert out.clinical_red_flag is True
    assert out.signals == ["loose tooth"]
    assert client.messages.create.call_count == 2


def test_exhausted_retries_raise():
    invalid = _resp({"clinical_red_flag": "nope"})
    client = SimpleNamespace(messages=SimpleNamespace(create=MagicMock(return_value=invalid)))
    with pytest.raises(ValidationError):
        structured_call(
            client, model="m", system="s", user="u",
            schema_model=ClinicalSafety, tool_name="clinical_safety", max_retries=1,
        )
    # initial attempt + 1 retry
    assert client.messages.create.call_count == 2
