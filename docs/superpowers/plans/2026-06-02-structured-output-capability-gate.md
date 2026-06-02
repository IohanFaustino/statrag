# Structured-Output Capability Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-model control that uses native `json_schema` structured output when the model supports it, and otherwise falls back to `json_object` + schema injected into the system message — applied to both `tutor` and `facilitate` modes.

**Architecture:** A new pure-function module `src/services/chat/llm/structured.py` holds a static capability table (`json_mode_for`) and a payload resolver (`resolve_response_format`). `facilitate._chat` and `tutor.build_agent` call the resolver to pick the strongest supported mode and, when falling back, append a compact schema hint to the system message. Existing `strip_fences`/`json.loads` parsing stays as a safety net.

**Tech Stack:** Python 3.12, Pydantic v2, OpenAI-compatible SDK, pytest.

---

## File Structure

- **Create** `src/services/chat/llm/structured.py` — capability table + resolver (one responsibility: decide structured-output mode per model).
- **Modify** `src/services/chat/schemas/output.py` — add `FacilitateMap`, `FacilitateVerify` Pydantic models (shapes for the two facilitate JSON calls).
- **Modify** `src/services/chat/agents/facilitate.py` — `_chat` grows a `schema=` param; MAP + VERIFY calls pass their schema.
- **Modify** `src/services/chat/mode_impls/tutor.py` — gate `response_format=TutorAnswer` on capability; append schema hint on fallback.
- **Create** `src/services/chat/tests/test_structured_output_gate.py` — unit tests for the gate.
- **Modify** `src/services/chat/tests/test_facilitate.py` — facilitate integration of the gate.
- **Create** `src/services/chat/tests/test_tutor_structured_gate.py` — tutor gate behavior.

Run all tests with: `.venv/bin/python -m pytest <path> -q`

---

### Task 1: Capability table + resolver

**Files:**
- Create: `src/services/chat/llm/structured.py`
- Test: `src/services/chat/tests/test_structured_output_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_structured_output_gate.py
"""Unit tests for the structured-output capability gate."""
from __future__ import annotations

import pydantic
import pytest

from src.services.chat.llm.structured import (
    JsonMode,
    json_mode_for,
    resolve_response_format,
)


class _Shape(pydantic.BaseModel):
    key_points: list[str]
    ok: bool


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-4o", JsonMode.SCHEMA),
        ("gpt-5.4-nano-2026-03-17", JsonMode.SCHEMA),
        ("gemini-2.5-flash", JsonMode.SCHEMA),
        ("qwen-plus", JsonMode.SCHEMA),
        ("moonshotai/kimi-k2-instruct-0905", JsonMode.SCHEMA),
        ("deepseek-v4-pro", JsonMode.OBJECT),
        ("deepseek-chat", JsonMode.OBJECT),
        ("meta-llama/llama-4-scout-17b-16e-instruct", JsonMode.OBJECT),
        ("llama-3.3-70b-versatile", JsonMode.OBJECT),
        ("openai/gpt-oss-120b", JsonMode.OBJECT),
        ("openai/gpt-oss-20b", JsonMode.OBJECT),
        ("some-unknown-model", JsonMode.OBJECT),
        (None, JsonMode.OBJECT),
    ],
)
def test_json_mode_for(model, expected):
    assert json_mode_for(model) is expected


def test_resolve_schema_model_uses_native_schema():
    payload, hint = resolve_response_format("gpt-4o", _Shape)
    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["schema"]["properties"].keys() >= {"key_points", "ok"}
    assert hint is None


def test_resolve_object_model_uses_json_object_plus_hint():
    payload, hint = resolve_response_format("deepseek-v4-pro", _Shape)
    assert payload == {"type": "json_object"}
    assert hint is not None
    assert "json" in hint.lower()
    assert "key_points" in hint and "ok" in hint


def test_resolve_none_schema_returns_nothing():
    payload, hint = resolve_response_format("deepseek-v4-pro", None)
    assert payload is None and hint is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_structured_output_gate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.chat.llm.structured'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/services/chat/llm/structured.py
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
    NONE = "none"            # nothing enforced


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


def _schema_payload(schema: type) -> dict | None:
    """Build the OpenAI ``json_schema`` response_format payload, or ``None``."""
    name = getattr(schema, "__name__", "Output")
    try:
        json_schema = schema.model_json_schema()  # type: ignore[attr-defined]
    except AttributeError:
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": json_schema,
            "strict": False,  # strict mode rejects many valid pydantic schemas
        },
    }


def _schema_hint(schema: type) -> str | None:
    """Compact instruction naming the JSON shape, for the system message.

    Contains the literal word "json" so DeepSeek/Qwen accept json_object mode.
    """
    try:
        js = schema.model_json_schema()  # type: ignore[attr-defined]
    except AttributeError:
        return None
    props = list((js.get("properties") or {}).keys())
    required = js.get("required") or props
    shape = json.dumps({k: "..." for k in props})
    return (
        "Return ONLY a valid json object with exactly these keys: "
        f"{', '.join(props)} (required: {', '.join(required)}). "
        f"Shape: {shape}"
    )


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
        Falls back to (None, hint) if the schema cannot be introspected.
    """
    if schema is None:
        return None, None
    mode = json_mode_for(model_id)
    if mode is JsonMode.SCHEMA:
        payload = _schema_payload(schema)
        if payload is not None:
            return payload, None
        logger.warning("schema introspection failed for %s; using hint", schema)
        return None, _schema_hint(schema)
    if mode is JsonMode.OBJECT:
        return {"type": "json_object"}, _schema_hint(schema)
    return None, _schema_hint(schema)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_structured_output_gate.py -q`
Expected: PASS (all parametrized + 3 resolver tests)

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/llm/structured.py src/services/chat/tests/test_structured_output_gate.py
git commit -m "feat(chat): structured-output capability gate (json_schema vs json_object+hint)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Facilitate schemas + `_chat` gate

**Files:**
- Modify: `src/services/chat/schemas/output.py`
- Modify: `src/services/chat/agents/facilitate.py:67-72` (`_chat`), `:78` (MAP call), `:158-160` (VERIFY call)
- Test: `src/services/chat/tests/test_facilitate.py`

- [ ] **Step 1: Add the facilitate output shapes**

Append to `src/services/chat/schemas/output.py` (use the existing import of
`pydantic.BaseModel`/`Field` already in that file):

```python
class FacilitateMap(BaseModel):
    """Shape of the facilitate MAP stage output."""

    key_points: list[str] = Field(default_factory=list)
    concepts: list[dict] = Field(default_factory=list)


class FacilitateVerify(BaseModel):
    """Shape of the facilitate VERIFY stage output."""

    fixed_body: str = ""
    ok: bool = False
    unsupported: list[str] = Field(default_factory=list)
    confidence: float = 0.5
```

- [ ] **Step 2: Write the failing test**

Add to `src/services/chat/tests/test_facilitate.py` (imports at top of file):

```python
from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.agents import facilitate as fac


@pytest.mark.asyncio
async def test_chat_object_model_injects_hint_and_json_object():
    captured = {}

    class _Resp:
        class _Choice:
            class _Msg:
                content = '{"key_points": [], "concepts": []}'
            message = _Msg()
        choices = [_Choice()]

    async def _create(**kwargs):
        captured.update(kwargs)
        return _Resp()

    client = AsyncMock()
    client.chat.completions.create = _create
    with patch.object(fac, "aclient_for", return_value=client):
        await fac._chat(
            [{"role": "system", "content": "BASE"},
             {"role": "user", "content": "u"}],
            model="deepseek-v4-pro", max_tokens=100,
            schema=fac.FacilitateMap,
        )
    assert captured["response_format"] == {"type": "json_object"}
    sys_msg = captured["messages"][0]["content"]
    assert "BASE" in sys_msg and "json" in sys_msg.lower()
    assert "key_points" in sys_msg


@pytest.mark.asyncio
async def test_chat_schema_model_leaves_system_untouched():
    captured = {}

    class _Resp:
        class _Choice:
            class _Msg:
                content = "{}"
            message = _Msg()
        choices = [_Choice()]

    async def _create(**kwargs):
        captured.update(kwargs)
        return _Resp()

    client = AsyncMock()
    client.chat.completions.create = _create
    with patch.object(fac, "aclient_for", return_value=client):
        await fac._chat(
            [{"role": "system", "content": "BASE"},
             {"role": "user", "content": "u"}],
            model="gpt-4o", max_tokens=100,
            schema=fac.FacilitateMap,
        )
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["messages"][0]["content"] == "BASE"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_facilitate.py -q -k chat_`
Expected: FAIL — `_chat() got an unexpected keyword argument 'schema'`

- [ ] **Step 4: Implement the `_chat` gate**

In `src/services/chat/agents/facilitate.py`, add imports near the existing
`from src.services.chat.llm.router import aclient_for`:

```python
from src.services.chat.llm.structured import resolve_response_format
from src.services.chat.schemas.output import FacilitateMap, FacilitateVerify
```

Replace `_chat` (lines 67-72) with:

```python
async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    oa = aclient_for(model)
    response_format, hint = resolve_response_format(model, schema)
    if hint:
        messages = [dict(m) for m in messages]
        for m in messages:
            if m.get("role") == "system":
                m["content"] = f"{m['content']}\n\n{hint}"
                break
    kwargs: dict = {
        "model": model, "messages": messages,
        "temperature": temperature, "max_completion_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = await oa.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
```

- [ ] **Step 5: Pass schema at the MAP + VERIFY call sites**

Line ~78 (MAP) — add `schema=FacilitateMap`:

```python
        raw = await _chat([{"role": "system", "content": FACILITATE_MAP_PROMPT},
                           {"role": "user", "content": user}], model=model,
                          max_tokens=500, schema=FacilitateMap)
```

Line ~158 (VERIFY) — add `schema=FacilitateVerify`:

```python
        raw = await _chat([{"role": "system", "content": FACILITATE_VERIFY_PROMPT},
                           {"role": "user", "content": f"SOURCE:\n{section_text[:_PREVIEW]}\n\nBODY:\n{body}"}],
                          model=model, max_tokens=1100, schema=FacilitateVerify)
```

(Leave `_explain`, `_intro`, `_teach` calls unchanged — `schema` defaults to `None`.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_facilitate.py -q`
Expected: PASS — new `_chat` tests + all pre-existing facilitate tests.

- [ ] **Step 7: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/agents/facilitate.py src/services/chat/tests/test_facilitate.py
git commit -m "feat(facilitate): apply structured-output gate to MAP + VERIFY calls

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Tutor gate

**Files:**
- Modify: `src/services/chat/mode_impls/tutor.py` (`build_agent`)
- Test: `src/services/chat/tests/test_tutor_structured_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_tutor_structured_gate.py
"""Tutor structured-output capability gate."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.services.chat.llm.structured import JsonMode
from src.services.chat.schemas.output import TutorAnswer


@pytest.mark.asyncio
async def test_schema_model_passes_response_format(monkeypatch):
    monkeypatch.delenv("TUTOR_FREE_TEXT", raising=False)
    from src.services.chat.mode_impls import tutor as t
    t.build_agent.cache_clear()
    captured = {}

    def _fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    with patch.object(t, "create_agent", _fake_create_agent), \
         patch.object(t, "json_mode_for", return_value=JsonMode.SCHEMA), \
         patch.object(t, "get_async_checkpointer", return_value=None):
        await t.build_agent()
    assert captured.get("response_format") is TutorAnswer
    assert captured["system_prompt"]  # unchanged base prompt is fine


@pytest.mark.asyncio
async def test_object_model_drops_schema_and_appends_hint(monkeypatch):
    monkeypatch.delenv("TUTOR_FREE_TEXT", raising=False)
    from src.services.chat.mode_impls import tutor as t
    t.build_agent.cache_clear()
    captured = {}

    def _fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    with patch.object(t, "create_agent", _fake_create_agent), \
         patch.object(t, "json_mode_for", return_value=JsonMode.OBJECT), \
         patch.object(t, "get_async_checkpointer", return_value=None):
        await t.build_agent()
    assert "response_format" not in captured
    assert "json" in captured["system_prompt"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_structured_gate.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'json_mode_for'`

- [ ] **Step 3: Implement the gate**

In `src/services/chat/mode_impls/tutor.py` add imports:

```python
from src.services.chat.llm.structured import JsonMode, json_mode_for, resolve_response_format
```

Replace the `kwargs` block in `build_agent` (the section that currently sets
`response_format` only when `TUTOR_FREE_TEXT` is unset) with:

```python
        model_id = settings.openai_model_nano
        system_prompt = TUTOR_INSTRUCTIONS
        kwargs: dict = {
            "model": f"openai:{model_id}",
            "tools": [retrieve],
            "checkpointer": await get_async_checkpointer(),
        }
        use_schema = (
            not os.environ.get("TUTOR_FREE_TEXT")
            and json_mode_for(model_id) is JsonMode.SCHEMA
        )
        if use_schema:
            kwargs["response_format"] = TutorAnswer
        elif not os.environ.get("TUTOR_FREE_TEXT"):
            _, hint = resolve_response_format(model_id, TutorAnswer)
            if hint:
                system_prompt = f"{system_prompt}\n\n{hint}"
        kwargs["system_prompt"] = system_prompt
        _AGENT = create_agent(**kwargs)
        return _AGENT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_structured_gate.py -q`
Expected: PASS — both branches.

- [ ] **Step 5: Run the broader chat test suite for regressions**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: PASS — no regressions (existing tutor, facilitate, scaffold tests green).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/mode_impls/tutor.py src/services/chat/tests/test_tutor_structured_gate.py
git commit -m "feat(tutor): gate response_format=TutorAnswer on model json_schema support

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Static capability registry → Task 1 (`json_mode_for`). ✔
- `resolve_response_format` returning `(payload, hint)` → Task 1. ✔
- json_object + schema-in-message fallback → Task 1 `_schema_hint`, used in Tasks 2 & 3. ✔
- Groq per-model granularity → Task 1 `_GROQ_OBJECT_IDS` / kimi prefix. ✔
- Facilitate MAP + VERIFY gated → Task 2. ✔
- Prose facilitate calls unchanged → Task 2 Step 5 note. ✔
- Tutor gate + defensive OBJECT branch → Task 3. ✔
- 9 deterministic tests → Task 1 (5 cases in one parametrize + 3 resolver), Task 2 (2), Task 3 (2). ✔
- No network in tests → all mocked / pure. ✔

**Placeholder scan:** none — every code step is complete.

**Type consistency:** `JsonMode`, `json_mode_for`, `resolve_response_format`, `FacilitateMap`, `FacilitateVerify` referenced identically across tasks. `_chat(..., schema=None)` signature matches call sites. `build_agent` keeps returning the cached agent.

**Note on `get_async_checkpointer` patch:** tutor tests patch it to `None`; `create_agent` is also patched so the `None` checkpointer is never used — safe.
