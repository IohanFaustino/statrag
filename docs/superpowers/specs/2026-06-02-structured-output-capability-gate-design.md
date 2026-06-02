# Structured-Output Capability Gate — Design

**Date:** 2026-06-02
**Status:** Approved (brainstorm)
**Scope:** `tutor` mode + `facilitate` mode JSON-producing LLM calls

## Problem

Every provider in this repo is reached through the OpenAI-compatible SDK, but
native structured-output support is **not uniform**:

| Provider (our models) | `json_object` | `json_schema` |
|---|---|---|
| OpenAI (gpt-4o, gpt-5.4) | ✅ | ✅ strict |
| DeepSeek (v4-pro/chat) | ✅ | ❌ |
| Groq (llama-4, llama-3.3, gpt-oss) | ✅ | ⚠️ only newer models (kimi); our models ignore/400 |
| Gemini 2.5 (OpenAI-compat) | ✅ | ✅ |
| Qwen (plus/turbo/max) | ✅ (msg must contain "json") | ✅ |

Today there is **no capability gate**:

- Each `BaseLLM` client unconditionally builds a `json_schema` payload, except
  `DeepSeekChat` which silently drops `response_format` entirely (no JSON
  enforcement at all).
- `facilitate._chat` passes **no** `response_format`; it relies on
  `strip_fences` + `json.loads` of free text.

Consequence: Groq llama / gpt-oss get a `json_schema` they ignore or reject;
DeepSeek gets nothing. Output reliability depends on the model picked.

## Goal

A single **control** that, per model, decides the strongest structured-output
mode the model actually supports, and degrades gracefully:

1. Model supports `json_schema` → send `response_format={"type":"json_schema", …}`.
2. Else → fall back to `response_format={"type":"json_object"}` **and** inject the
   expected JSON shape/schema into the system message ("use it as a message").
3. (Both fallbacks keep the existing `strip_fences` + `json.loads` parse as a
   belt-and-suspenders safety net.)

Applied to **tutor** and **facilitate**.

## Approach (chosen)

- **Detection:** static capability registry (deterministic, zero added latency,
  unit-testable). Groq needs **per-model** granularity.
- **Fallback:** `json_object` + schema injected into the system message.
- **Sharing:** one shared helper in `src/services/chat/llm/`, used by both modes.

Rejected: runtime try-then-fallback (wasted call + non-deterministic tests);
per-mode duplicated logic (capability table drift).

## Components

### 1. `src/services/chat/llm/structured.py` (new)

The single source of truth.

```python
from enum import Enum

class JsonMode(str, Enum):
    SCHEMA = "json_schema"   # native schema-constrained decoding
    OBJECT = "json_object"   # JSON mode, no schema enforcement
    NONE   = "none"          # provider enforces nothing

# Capability table. Default per provider; per-model overrides where a
# provider's support is model-specific (Groq).
def json_mode_for(model_id: str | None) -> JsonMode: ...

def resolve_response_format(
    model_id: str | None,
    schema: type | None,
) -> tuple[dict | None, str | None]:
    """Return (response_format_payload, schema_hint_text).

    - SCHEMA: ({"type":"json_schema", "json_schema":{...}}, None)
    - OBJECT: ({"type":"json_object"}, "<schema-as-text to append to system msg>")
    - NONE:   (None, "<schema-as-text to append to system msg>")

    schema_hint_text is None when the response_format already constrains output
    (SCHEMA), otherwise a compact instruction containing the literal word "json"
    plus the JSON shape (satisfies DeepSeek/Qwen "must contain json" rule).
    """
```

Capability table (initial):

| Match | Mode |
|---|---|
| `gpt-*`, default OpenAI | SCHEMA |
| `gemini-*` | SCHEMA |
| `qwen-*` | SCHEMA |
| Groq `moonshotai/kimi-*` (future) | SCHEMA |
| Groq `llama-*`, `openai/gpt-oss-*` | OBJECT |
| `deepseek-*` | OBJECT |
| unknown | OBJECT (safe lowest common denominator) |

Schema-as-text builder: `model_json_schema()` rendered into a short
`"Return ONLY a JSON object matching this schema (json): { … }"` string.

### 2. `facilitate._chat` (modified)

`_chat(messages, *, model, max_tokens, temperature, schema=None)`:

- Call `resolve_response_format(model, schema)`.
- If a `response_format` payload is returned, pass it to
  `chat.completions.create`.
- If `schema_hint_text` is returned, append it to the **system** message content
  (the first `{"role":"system"}` message) before sending.
- Keep `strip_fences` + `json.loads` at call sites unchanged.

Apply `schema` to the two JSON calls:
- `_map_section` → a `FacilitateMap` shape (`key_points`, `concepts[]`).
- `_verify` → a `FacilitateVerify` shape (`fixed_body`, `ok`, `unsupported`,
  `confidence`).

`_explain`, `_intro`, `_teach` return free prose → `schema=None`, no
`response_format` (NONE-style, unchanged behavior).

### 3. Tutor path (modified)

`mode_impls/tutor.py::build_agent` currently always sets
`response_format=TutorAnswer` (LangChain `create_agent`) on an OpenAI-pinned
model.

- Gate it: `if json_mode_for(model) is JsonMode.SCHEMA and not TUTOR_FREE_TEXT:`
  pass `response_format=TutorAnswer` (current behavior).
- Else: omit the LangChain `response_format`, and **append the TutorAnswer
  schema hint** to `TUTOR_INSTRUCTIONS` so the model still aims at the shape.
- Today's tutor model is always OpenAI → SCHEMA branch; the OBJECT branch is
  **defensive** (exercised only when the configured model is non-schema). It is
  implemented and unit-tested via a mocked `json_mode_for`.

No change to `TutorAnswer` schema or the SSE contract.

## Data flow

```
caller (facilitate._chat / tutor.build_agent)
  → resolve_response_format(model, schema)
      → json_mode_for(model)         # static table lookup
      → (response_format?, hint_text?)
  → inject hint_text into system msg (when present)
  → create(..., response_format=payload?)
  → strip_fences + json.loads (facilitate)  /  LangChain parse (tutor)
```

## Error handling

- Unknown model → OBJECT (never crash, never silently send an unsupported
  schema).
- `model_json_schema()` failure → treat as NONE (no payload, no hint), log,
  preserve current free-text behavior.
- No new exceptions surface to the SSE stream; existing `try/except` in
  `_map_section`/`_verify` still guards parse failures.

## Testing

New `src/services/chat/tests/test_structured_output_gate.py`:

1. `json_mode_for` returns SCHEMA for gpt/gemini/qwen, OBJECT for
   deepseek + groq-llama + groq-gpt-oss, OBJECT for unknown.
2. `resolve_response_format` with a SCHEMA model → payload `type==json_schema`,
   `hint_text is None`.
3. `resolve_response_format` with an OBJECT model → payload
   `{"type":"json_object"}`, `hint_text` contains the literal word "json" and
   the schema's top-level keys.
4. `resolve_response_format(schema=None)` → `(None, None)`.

Facilitate (`test_facilitate.py` additions, mocked `_chat`/client):

5. With an OBJECT model, `_map_section` sends `response_format` json_object and
   the system message gained the schema hint.
6. With a SCHEMA model, the system message is **unchanged** and the payload is
   json_schema.
7. Existing facilitate digest tests still pass (parse path intact).

Tutor (`test_t18_xml_scaffolds.py` or new `test_tutor_structured_gate.py`):

8. SCHEMA model → `build_agent` kwargs include `response_format=TutorAnswer`.
9. OBJECT model (mocked `json_mode_for`) → kwargs omit `response_format` and the
   system_prompt gained the TutorAnswer schema hint.

All tests deterministic — no network; capability table + payload shaping are
pure functions; agent/client interaction mocked.

## Out of scope (YAGNI)

- Runtime probing of provider capabilities.
- Changing `resume`/`qa` modes.
- Altering the `BaseLLM` per-client `_build_response_format` helpers (the new
  gate sits in front of the facilitate + tutor call sites; per-client helpers
  remain for the streaming `BaseLLM` path and are unaffected). A future
  follow-up may route those through the same registry.
```
