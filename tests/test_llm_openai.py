"""OpenAI-compatible provider path: forced function call -> validate -> retry (mocked client)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from vigil import config, llm
from vigil.schemas import ClinicalSafety


@pytest.fixture
def openai_provider(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")


def _tool_call(arguments: str, call_id: str = "c1"):
    fn = SimpleNamespace(name="clinical_safety", arguments=arguments)
    call = SimpleNamespace(id=call_id, type="function", function=fn)
    message = SimpleNamespace(tool_calls=[call], content=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _client(*responses):
    create = MagicMock(side_effect=list(responses))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create


def test_openai_path_parses_function_arguments(openai_provider):
    client, create = _client(
        _tool_call(json.dumps({"clinical_red_flag": True, "signals": ["loose tooth"], "confidence": 0.9}))
    )
    out = llm.structured_call(
        client, model="kimi", system="s", user="u",
        schema_model=ClinicalSafety, tool_name="clinical_safety",
    )
    assert out.clinical_red_flag is True and out.signals == ["loose tooth"]
    # forced a specific function
    kwargs = create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "function", "function": {"name": "clinical_safety"}}


def test_openai_path_retries_on_validation_error(openai_provider):
    client, create = _client(
        _tool_call(json.dumps({"clinical_red_flag": "not-a-bool"}), "a"),
        _tool_call(json.dumps({"clinical_red_flag": False, "signals": [], "confidence": 0.2}), "b"),
    )
    out = llm.structured_call(
        client, model="kimi", system="s", user="u",
        schema_model=ClinicalSafety, tool_name="clinical_safety", max_retries=1,
    )
    assert out.clinical_red_flag is False
    assert create.call_count == 2


def test_openai_path_raises_after_retries(openai_provider):
    client, create = _client(
        _tool_call(json.dumps({"clinical_red_flag": "nope"})),
        _tool_call(json.dumps({"clinical_red_flag": "still-nope"})),
    )
    with pytest.raises(ValidationError):
        llm.structured_call(
            client, model="kimi", system="s", user="u",
            schema_model=ClinicalSafety, tool_name="clinical_safety", max_retries=1,
        )
    assert create.call_count == 2
