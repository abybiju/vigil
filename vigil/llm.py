"""One reusable structured-output helper used by every model pass.

Primary path: native strict tool use (forced single tool, grammar-constrained to the schema).
Defense-in-depth: Pydantic validation + one retry (the validation error is fed back). If the
API rejects the strict schema, we transparently fall back to non-strict forced tool use — the
Pydantic validation + retry still guarantee a well-formed result.
"""

from __future__ import annotations

from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from . import config

T = TypeVar("T", bound=BaseModel)

# JSON-schema keywords not allowed in strict tool-use schemas (range/length/format/pattern),
# plus metadata we drop to keep the schema lean.
_DROP_KEYS = {
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "minItems", "maxItems",
    "pattern", "format", "title", "default",
}


def get_client():
    """Return an Anthropic client, or an OpenAI client pointed at any OpenAI-compatible endpoint."""
    if config.LLM_PROVIDER == "openai":
        from openai import OpenAI

        return OpenAI(
            base_url=config.LLM_BASE_URL,
            api_key=config.require_api_key(),
            timeout=config.REQUEST_TIMEOUT,
            max_retries=config.MAX_RETRIES,
        )
    # Bounded timeout + retries so a stalled socket can never hang the eval indefinitely.
    return anthropic.Anthropic(
        api_key=config.require_api_key(),
        timeout=config.REQUEST_TIMEOUT,
        max_retries=config.MAX_RETRIES,
    )


def _inline_refs(node: Any, defs: dict) -> Any:
    """Resolve $ref against $defs so the schema is self-contained (strict mode needs this)."""
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            resolved = _inline_refs(defs.get(name, {}), defs)
            merged = dict(resolved)
            for k, v in node.items():
                if k != "$ref":
                    merged[k] = _inline_refs(v, defs)
            return merged
        return {k: _inline_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(x, defs) for x in node]
    return node


def _clean(node: Any) -> Any:
    """Drop unsupported keywords and force additionalProperties:false on every object."""
    if isinstance(node, dict):
        out = {k: _clean(v) for k, v in node.items() if k not in _DROP_KEYS}
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_clean(x) for x in node]
    return node


def schema_for(model: type[BaseModel]) -> dict:
    """Strict-tool-use-valid JSON schema for a Pydantic model (refs inlined, keywords pruned)."""
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    body = {k: v for k, v in raw.items() if k != "$defs"}
    return _clean(_inline_refs(body, defs))


def _strip_additional_properties(node: Any) -> Any:
    """Drop additionalProperties:false (server-side validators reject extra keys; Pydantic ignores them)."""
    if isinstance(node, dict):
        return {k: _strip_additional_properties(v) for k, v in node.items() if k != "additionalProperties"}
    if isinstance(node, list):
        return [_strip_additional_properties(x) for x in node]
    return node


def structured_call(
    client,
    *,
    model: str,
    system: str,
    user: str,
    schema_model: type[T],
    tool_name: str,
    max_tokens: int = 1024,
    temperature: float | None = None,
    max_retries: int = 1,
) -> T:
    """Force a single tool call and return a validated `schema_model` instance.

    Dispatches on the configured provider: Anthropic native (strict) tool use, or an
    OpenAI-compatible function call (Groq/Moonshot/Gemini/DeepSeek/OpenRouter/…).
    """
    if temperature is None:
        temperature = config.TEMPERATURE
    if config.LLM_PROVIDER == "openai":
        return _openai_structured_call(
            client, model=model, system=system, user=user, schema_model=schema_model,
            tool_name=tool_name, max_tokens=max_tokens, temperature=temperature, max_retries=max_retries,
        )
    return _anthropic_structured_call(
        client, model=model, system=system, user=user, schema_model=schema_model,
        tool_name=tool_name, max_tokens=max_tokens, temperature=temperature, max_retries=max_retries,
    )


def _anthropic_structured_call(
    client,
    *,
    model: str,
    system: str,
    user: str,
    schema_model: type[T],
    tool_name: str,
    max_tokens: int,
    temperature: float,
    max_retries: int,
) -> T:
    schema = schema_for(schema_model)
    messages: list[dict] = [{"role": "user", "content": user}]
    use_strict = True
    attempts_left = max_retries
    last_err: Exception | None = None

    while True:
        tool: dict = {
            "name": tool_name,
            "description": f"Return a {schema_model.__name__} object.",
            "input_schema": schema,
        }
        if use_strict:
            tool["strict"] = True

        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
                messages=messages,
            )
        except anthropic.BadRequestError as e:
            msg = str(getattr(e, "message", "") or e).lower()
            schema_related = any(k in msg for k in ("schema", "strict", "input_schema", "tool"))
            if use_strict and schema_related:
                use_strict = False  # strict schema rejected — retry non-strict (free, not a validation retry)
                continue
            raise  # auth/credit/other 400s propagate immediately

        block = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        if block is None:
            raise RuntimeError(
                f"Model did not call tool '{tool_name}' (stop_reason={getattr(resp, 'stop_reason', '?')})."
            )

        try:
            return schema_model.model_validate(block.input)
        except ValidationError as e:
            last_err = e
            if attempts_left <= 0:
                raise
            attempts_left -= 1
            messages += [
                {"role": "assistant", "content": resp.content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "is_error": True,
                            "content": f"Your arguments failed validation:\n{e}\nReturn corrected arguments that match the schema.",
                        }
                    ],
                },
            ]

    raise last_err or RuntimeError("structured_call failed")  # pragma: no cover


def _openai_structured_call(
    client,
    *,
    model: str,
    system: str,
    user: str,
    schema_model: type[T],
    tool_name: str,
    max_tokens: int,
    temperature: float,
    max_retries: int,
) -> T:
    """OpenAI-compatible function calling: force one tool call, validate, retry on error.

    Robust to weaker open models on shared endpoints (Groq etc.): the provider validates tool
    args server-side and 400s if they don't match the schema, and a model may emit no tool call
    at all. Both are retried (with a temperature nudge so the retry differs), and the schema sent
    to the provider drops `additionalProperties:false` (Pydantic ignores extra keys anyway), which
    is the most common cause of those server-side rejections.
    """
    tool = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": f"Return a {schema_model.__name__} object.",
            "parameters": _strip_additional_properties(schema_for(schema_model)),
        },
    }
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    attempts_left = max_retries
    tool_call_attempts = max_retries + 2  # extra tries if the provider rejects/omits the tool call
    temp = temperature

    while True:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": tool_name}},
                temperature=temp,
                max_tokens=max_tokens,
            )
        except Exception as e:
            retryable = any(k in str(e).lower() for k in ("tool_use_failed", "did not match schema", "tool call validation"))
            if retryable and tool_call_attempts > 1:
                tool_call_attempts -= 1
                temp = max(temp, 0.4)  # vary the output so a deterministic-ish retry can differ
                continue
            raise
        message = resp.choices[0].message
        calls = getattr(message, "tool_calls", None) or []
        if not calls:
            if tool_call_attempts > 1:
                tool_call_attempts -= 1
                temp = max(temp, 0.4)
                continue
            raise RuntimeError(f"Model did not call tool '{tool_name}'.")
        args = calls[0].function.arguments

        try:
            return schema_model.model_validate_json(args)
        except ValidationError as e:
            if attempts_left <= 0:
                raise
            attempts_left -= 1
            messages += [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": calls[0].id, "type": "function", "function": {"name": tool_name, "arguments": args}}
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": calls[0].id,
                    "content": f"Your arguments failed validation:\n{e}\nReturn corrected arguments that match the schema.",
                },
            ]
