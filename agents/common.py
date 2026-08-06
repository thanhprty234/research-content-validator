"""Shared helpers for agents: prompt loading and structured LLM calls."""

import os
from pathlib import Path
from typing import Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

MAX_STRUCTURED_ATTEMPTS = 3


def load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _retryable(exc: Exception) -> bool:
    """Whether a call failure is worth retrying.

    Only retry malformed structured output (pydantic ValidationError) and
    transient/provider errors (HTTP 429 rate-limit, 5xx). Permanent 4xx errors
    (401, 402 low credits, 403) are not retried — they would only waste calls
    and cost credits.
    """
    if isinstance(exc, ValidationError):
        return True
    if isinstance(exc, OutputParserException):
        return True
    status = getattr(exc, "status_code", None)
    if status is None and hasattr(exc, "response"):
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status >= 500 or status == 429
    # network/timeout wrappers -> transient
    exc_name = type(exc).__name__.lower()
    return any(k in exc_name for k in ("timeout", "connection", "apicallerror"))


_STRUCTURED_METHODS = ("default", "json", "prompt")


def _invoke_structured(llm, schema, system, user, max_tokens, method):
    """Invoke the LLM with a specific structured-output method.

    ``default`` uses langchain's smart schema-constrained output (JSON schema
    via response_format, with tool-calling / json fallbacks). ``json`` forces
    ``method="json_mode"`` which only asks for a JSON object. ``prompt`` does a
    plain call and parses JSON out of the reply — for providers that support
    none of the response_format variants.
    """
    from langchain_core.output_parsers import JsonOutputParser

    if method == "prompt":
        target = llm.bind(max_tokens=max_tokens) if max_tokens else llm
        blobs = target.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        parsed = JsonOutputParser().parse(blobs.content)
        return schema(**parsed)

    if method == "json":
        target = llm.with_structured_output(schema, method="json_mode")
    else:
        target = llm.with_structured_output(schema)
    if max_tokens:
        target = target.bind(max_tokens=max_tokens)
    return target.invoke(
        [SystemMessage(content=system), HumanMessage(content=user)]
    )


def _should_method_fallback(exc, remaining_methods) -> bool:
    """True if the provider rejected this structured-output method and others remain."""
    if not remaining_methods:
        return False
    msg = str(exc).lower()
    return "response_format" in msg or "unavailable" in msg or "not supported" in msg


def structured_call(llm, schema: type[BaseModel], system: str, user: str, max_tokens: Optional[int] = None):
    """Invoke an LLM with schema-constrained output.

    Some cheap/free models occasionally return truncated or malformed JSON for
    the schema, so the call is retried with a strict instruction on failure.

    The structured-output method adapts if the model rejects it: we try
    ``default`` first, then ``json``, then ``prompt`` — this accommodates free /
    provider-hosted models (e.g. OpenCode Zen free tier) that don't support
    ``response_format``. See `_STRUCTURED_METHODS`.

    Args:
        llm: A langchain chat model.
        schema: A Pydantic model describing the expected structured output.
        system: The system prompt.
        user: The user message.
        max_tokens: Optional output-token cap for this call. Use a value tuned to
            the schema's size to avoid over-reserving credits on pay-per-token
            providers (OpenRouter reserves the full max_tokens budget per call).
            The global MODEL_MAX_TOKENS env var (if set) caps this value.
    """
    env_cap = os.getenv("MODEL_MAX_TOKENS")
    if env_cap:
        try:
            max_tokens = min(int(env_cap), max_tokens or int(env_cap))
        except ValueError:
            pass

    last_error = None
    methods = list(_STRUCTURED_METHODS)
    for method in methods:
        remaining = methods[methods.index(method) + 1:]
        for attempt in range(1, MAX_STRUCTURED_ATTEMPTS + 1):
            try:
                return _invoke_structured(llm, schema, system, user, max_tokens, method)
            except Exception as exc:
                last_error = exc
                if _retryable(exc):
                    if attempt < MAX_STRUCTURED_ATTEMPTS:
                        # same method, stricter instruction
                        user = (
                            f"{user}\n\n"
                            "The previous response was invalid JSON. "
                            "Reply with ONLY a single valid JSON object matching the schema exactly. "
                            "Do not truncate the response, do not add markdown fences, no trailing text."
                        )
                        continue
                    # exhausted retries for this method — fall back if provider rejects method
                    if _should_method_fallback(exc, remaining):
                        break
                    raise
                # non-retryable: only move to another method if this looks like a
                # "provider doesn't support structured output" rejection
                if _should_method_fallback(exc, remaining):
                    break
                raise
        # if the method broke out of its retry loop to fall back
        if _should_method_fallback(last_error, remaining):
            continue
        break
    raise last_error