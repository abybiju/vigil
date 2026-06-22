"""Central configuration. Reads env (with a .env fallback) and pins model IDs in one place."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # load .env if present; real env vars still win

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = ROOT / "migrations" / "001_init.sql"


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


# --- LLM provider ---
# anthropic (default — native strict tool use; what the eval proof was run on) OR
# openai (any OpenAI-compatible endpoint: Groq, Moonshot, Gemini, DeepSeek, OpenRouter, …)
LLM_PROVIDER = _get("VIGIL_LLM_PROVIDER", "anthropic").lower()
# Defaults point at Groq's free tier (OpenAI-compatible tool calling). gpt-oss-120b is a strong,
# always-available free model; verified handling Vigil's structured schemas + the clinical gate.
LLM_BASE_URL = _get("VIGIL_LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = _get("VIGIL_LLM_MODEL", "openai/gpt-oss-120b")
LLM_API_KEY = os.environ.get("VIGIL_LLM_API_KEY") or os.environ.get("GROQ_API_KEY")

# --- Models ---
if LLM_PROVIDER == "openai":
    # Use the provider's model for both passes; the claude-specific VIGIL_*_MODEL vars (which may
    # linger in .env) are ignored here — set VIGIL_LLM_MODEL to change the OpenAI-compatible model.
    TRIAGE_MODEL = LLM_MODEL
    CLINICAL_MODEL = LLM_MODEL
else:
    TRIAGE_MODEL = _get("VIGIL_TRIAGE_MODEL", "claude-sonnet-4-6")
    CLINICAL_MODEL = _get("VIGIL_CLINICAL_MODEL", "claude-sonnet-4-6")
PREFILTER_MODEL = _get("VIGIL_PREFILTER_MODEL", "claude-haiku-4-5-20251001")

# --- Behaviour ---
TEMPERATURE = float(_get("VIGIL_TEMPERATURE", "0"))
PROMPT_VERSION = _get("VIGIL_PROMPT_VERSION", "v2")
SCHEMA_VERSION = _get("VIGIL_SCHEMA_VERSION", "v1")

# --- Storage / retrieval ---
DB_PATH = Path(_get("VIGIL_DB_PATH", str(ROOT / "vigil.db")))
EMBEDDER = _get("VIGIL_EMBEDDER", "tfidf")  # tfidf | fastembed

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Per-request timeout (seconds) and SDK-level retry count — a stalled socket must never hang a run.
REQUEST_TIMEOUT = float(_get("VIGIL_REQUEST_TIMEOUT", "60"))
MAX_RETRIES = int(_get("VIGIL_MAX_RETRIES", "3"))

# Retrieval threshold above which a deterministic, grounded auto-draft is allowed.
RETRIEVAL_AUTOSEND_THRESHOLD = float(_get("VIGIL_RETRIEVAL_THRESHOLD", "0.30"))

# The framing guardrail caption that must appear on every generated draft/response.
HUMAN_GATE_CAPTION = (
    "Decision-support draft — pending human review. "
    "Vigil flags and structures; a human decides reportability. "
    "This is not an authoritative MDR determination."
)


def has_api_key() -> bool:
    return bool(LLM_API_KEY if LLM_PROVIDER == "openai" else ANTHROPIC_API_KEY)


def require_api_key() -> str:
    """Return the active provider's API key or raise a clear, actionable error."""
    if LLM_PROVIDER == "openai":
        if not LLM_API_KEY:
            raise RuntimeError(
                "No LLM key set. For the openai provider, set VIGIL_LLM_API_KEY (or GROQ_API_KEY). "
                "Free Groq key: https://console.groq.com/"
            )
        return LLM_API_KEY
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key "
            "(get one at https://console.anthropic.com/), or switch to a free provider with "
            "VIGIL_LLM_PROVIDER=openai + GROQ_API_KEY."
        )
    return ANTHROPIC_API_KEY
