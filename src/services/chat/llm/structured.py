"""Per-model structured-output capability gate.

Decides the strongest structured-output mode a model actually supports and
shapes the OpenAI ``response_format`` payload accordingly. When native
``json_schema`` is unsupported, callers fall back to ``json_object`` plus a
compact schema hint appended to the system message ("use it as a message").

Provider support (June 2026):
- OpenAI / Gemini / Qwen          -> json_schema
- Groq newer models (kimi-*)      -> json_schema
- Groq llama-* / gpt-oss-*        -> json_object only
- DeepSeek                        -> json_object only (no schema)
- unknown                         -> json_object (safe lowest common denominator)

NOTE: ``strict=False`` is used in json_schema payloads because strict mode
rejects many valid pydantic schemas (e.g. those with optional fields or
``$defs`` references).

Chinese-wall: imports only stdlib + pydantic. No src.* imports.
"""
from __future__ import annotations

import json
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class JsonMode(str, Enum):
    """Structured-output capability of a model."""

    SCHEMA = "json_schema"   # native schema-constrained decoding
    OBJECT = "json_object"   # JSON mode, no schema enforcement


# Groq is the only provider whose support is per-model, so it needs explicit
# membership sets rather than a prefix rule.
_GROQ_SCHEMA_PREFIXES: tuple[str, ...] = ("moonshotai/kimi",)
_GROQ_OBJECT_IDS: frozenset[str] = frozenset(
    {
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    }
)


def json_mode_for(model_id: str | None) -> JsonMode:
    """Return the strongest structured-output mode *model_id* supports.

    Args:
        model_id: Model identifier, or ``None``.

    Returns:
        :class:`JsonMode` — SCHEMA when native json_schema is supported,
        otherwise OBJECT (the safe default for unknown / object-only models).
    """
    if not model_id:
        return JsonMode.OBJECT
    if model_id in _GROQ_OBJECT_IDS:
        return JsonMode.OBJECT
    if any(model_id.startswith(p) for p in _GROQ_SCHEMA_PREFIXES):
        return JsonMode.SCHEMA
    if model_id.startswith("deepseek"):
        return JsonMode.OBJECT
    if (
        model_id.startswith("gpt-")
        or model_id.startswith("gemini")
        or model_id.startswith("qwen")
    ):
        return JsonMode.SCHEMA
    return JsonMode.OBJECT


def _get_json_schema(schema: type) -> dict | None:
    """Attempt to extract the JSON schema dict from a pydantic model class.

    Returns ``None`` if *schema* is not a pydantic model (no
    ``model_json_schema`` method), so callers can treat introspection failure
    uniformly without catching exceptions.
    """
    try:
        return schema.model_json_schema()  # type: ignore[attr-defined]
    except AttributeError:
        return None


def _schema_payload(name: str, js: dict) -> dict:
    """Build the OpenAI ``json_schema`` response_format payload."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": js,
            "strict": False,  # strict mode rejects many valid pydantic schemas
        },
    }


def _schema_hint(js: dict) -> str:
    """Compact instruction naming the JSON shape, for the system message.

    Contains the literal word "json" so DeepSeek/Qwen accept json_object mode.
    """
    props = list((js.get("properties") or {}).keys())
    required = js.get("required") or props
    shape = json.dumps({k: "..." for k in props})
    return (
        "Return ONLY a valid json object with exactly these keys: "
        f"{', '.join(props)} (required: {', '.join(required)}). "
        f"Shape: {shape}"
    )


def schema_hint(schema: type) -> str | None:
    """Build a compact "return only json with these keys" instruction.

    Safe to append to a system message in json_object / fallback mode so a
    model without native json_schema still aims at the right shape.

    Args:
        schema: Pydantic model class describing the desired output.

    Returns:
        The hint string, or ``None`` if *schema* is not introspectable.
    """
    js = _get_json_schema(schema)
    if js is None:
        return None
    return _schema_hint(js)


def resolve_response_format(
    model_id: str | None,
    schema: type | None,
) -> tuple[dict | None, str | None]:
    """Pick the response_format payload + optional system-message hint.

    Args:
        model_id: Model that will receive the request.
        schema: Pydantic model class describing the desired output, or ``None``
            for free-text calls.

    Returns:
        ``(response_format_payload, hint_text)``:
        - SCHEMA model + schema  -> (json_schema payload, None)
        - OBJECT model + schema  -> ({"type": "json_object"}, hint string)
        - any model, schema=None -> (None, None)
        - non-pydantic schema    -> (None, None) — cannot introspect
    """
    if schema is None:
        return None, None
    js = _get_json_schema(schema)
    if js is None:
        logger.warning("schema introspection failed for %s; skipping structured output", schema)
        return None, None
    name = getattr(schema, "__name__", "Output")
    mode = json_mode_for(model_id)
    if mode is JsonMode.SCHEMA:
        return _schema_payload(name, js), None
    # JsonMode.OBJECT
    return {"type": "json_object"}, _schema_hint(js)
