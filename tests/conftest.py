"""Test defaults: pin the LLM provider to 'anthropic' so the ambient .env (which may set
VIGIL_LLM_PROVIDER=openai for the live demo) never changes which code path the mocked
unit tests exercise. Tests that target the OpenAI-compatible path override this themselves.
"""

import pytest

from vigil import config


@pytest.fixture(autouse=True)
def _default_anthropic_provider(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
