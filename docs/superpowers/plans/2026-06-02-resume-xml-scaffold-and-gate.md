# Resume XML Scaffold + Structured-Output Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the XML-prompt scaffold + per-model structured-output gate to `resume` mode's five chapter stages, with the json fallback wrapped in a dedicated `<response_format>` token, and retrofit facilitate/tutor to the same token.

**Architecture:** Wrap the schema hint inside `structured._schema_hint` so every caller emits `<response_format>…</response_format>`. Add `structured.apply_structured_output(messages, model, schema)` to centralize resolve+inject, and route the three `_chat` seams (facilitate, chapter, _scope) through it. Add five `Chapter*` Pydantic schemas; scaffold the five `CHAPTER_*` prompts.

**Tech Stack:** Python 3.12, Pydantic v2, OpenAI-compatible SDK, pytest.

---

## File Structure

- **Modify** `src/services/chat/llm/structured.py` — `_schema_hint` emits `<response_format>` token; new `apply_structured_output`.
- **Modify** `src/services/chat/schemas/output.py` + `schemas/__init__.py` — five `Chapter*` models.
- **Modify** `src/services/chat/prompts/chapter.py` — XML-scaffold the 5 `CHAPTER_*` prompts.
- **Modify** `src/services/chat/agents/chapter.py` — `_chat(schema=)` via `apply_structured_output`; wire schemas at 4 call sites.
- **Modify** `src/services/chat/agents/_scope.py` — `_chat(schema=)` via `apply_structured_output`; `resolve_book` passes `ChapterParse`.
- **Modify** `src/services/chat/agents/facilitate.py` — `_chat` uses `apply_structured_output` (retrofit).
- **Tests:** extend `test_structured_output_gate.py`; new `test_chapter_gate.py`, `test_scope_gate.py`; extend `test_t18_xml_scaffolds.py`.

Run tests with `.venv/bin/python -m pytest <path> -q`.

---

### Task 1: `<response_format>` token + `apply_structured_output`

**Files:**
- Modify: `src/services/chat/llm/structured.py`
- Test: `src/services/chat/tests/test_structured_output_gate.py`

- [ ] **Step 1: Write the failing tests** (append to `test_structured_output_gate.py`)

```python
def test_schema_hint_wrapped_in_response_format_token():
    from src.services.chat.llm.structured import schema_hint

    class _S(pydantic.BaseModel):
        a: int
        b: str
    h = schema_hint(_S)
    assert h is not None
    assert h.strip().startswith("<response_format>")
    assert h.strip().endswith("</response_format>")
    assert "json" in h.lower() and "a" in h and "b" in h


def test_apply_structured_output_object_model_injects_token():
    from src.services.chat.llm.structured import apply_structured_output

    class _S(pydantic.BaseModel):
        a: int
    msgs = [{"role": "system", "content": "BASE"},
            {"role": "user", "content": "u"}]
    out_msgs, rf = apply_structured_output(msgs, "deepseek-v4-pro", _S)
    assert rf == {"type": "json_object"}
    assert "BASE" in out_msgs[0]["content"]
    assert "<response_format>" in out_msgs[0]["content"]
    # original not mutated
    assert msgs[0]["content"] == "BASE"


def test_apply_structured_output_schema_model_untouched():
    from src.services.chat.llm.structured import apply_structured_output

    class _S(pydantic.BaseModel):
        a: int
    msgs = [{"role": "system", "content": "BASE"}]
    out_msgs, rf = apply_structured_output(msgs, "gpt-4o", _S)
    assert rf["type"] == "json_schema"
    assert out_msgs[0]["content"] == "BASE"


def test_apply_structured_output_no_system_message_prepends():
    from src.services.chat.llm.structured import apply_structured_output

    class _S(pydantic.BaseModel):
        a: int
    msgs = [{"role": "user", "content": "u"}]
    out_msgs, rf = apply_structured_output(msgs, "deepseek-v4-pro", _S)
    assert out_msgs[0]["role"] == "system"
    assert "<response_format>" in out_msgs[0]["content"]
    assert out_msgs[-1]["role"] == "user"


def test_apply_structured_output_no_schema_noop():
    from src.services.chat.llm.structured import apply_structured_output

    msgs = [{"role": "system", "content": "BASE"}]
    out_msgs, rf = apply_structured_output(msgs, "gpt-4o", None)
    assert rf is None
    assert out_msgs[0]["content"] == "BASE"
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_structured_output_gate.py -q -k "response_format_token or apply_structured"`
Expected: FAIL — `cannot import name 'apply_structured_output'` and the wrap assertion fails.

- [ ] **Step 3: Implement**

In `src/services/chat/llm/structured.py`, change `_schema_hint` to wrap the body in the token. Replace its `return (...)` with:

```python
    body = (
        "Return ONLY a valid json object with exactly these keys: "
        f"{', '.join(props)} (required: {', '.join(required)}). "
        f"Shape: {shape}"
    )
    return f"<response_format>\n{body}\n</response_format>"
```

Add at the end of the module:

```python
def apply_structured_output(
    messages: list[dict],
    model_id: str | None,
    schema: type | None,
) -> tuple[list[dict], dict | None]:
    """Resolve the response_format and inject the fallback hint token.

    Centralizes the gate for every ``chat.completions.create`` call site. When
    the model lacks native ``json_schema``, the ``<response_format>`` hint is
    appended to the first system message (a system message is prepended when
    none exists). The input list is never mutated.

    Args:
        messages: OpenAI-style message dicts.
        model_id: Model that will receive the request.
        schema: Pydantic output schema, or ``None`` for free-text calls.

    Returns:
        ``(messages, response_format_payload)`` — *messages* is the original
        list when no injection happened, otherwise a new list.
    """
    response_format, hint = resolve_response_format(model_id, schema)
    if not hint:
        return messages, response_format
    new_messages = [dict(m) for m in messages]
    for m in new_messages:
        if m.get("role") == "system":
            m["content"] = f"{m['content']}\n\n{hint}"
            break
    else:
        new_messages.insert(0, {"role": "system", "content": hint})
    return new_messages, response_format
```

- [ ] **Step 4: Run, verify PASS (and no regressions in the file)**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_structured_output_gate.py -q`
Expected: PASS (new + existing — existing assertions check substrings "json"/keys which still hold).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/llm/structured.py src/services/chat/tests/test_structured_output_gate.py
git commit -m "feat(chat): wrap json fallback hint in <response_format> token + apply_structured_output helper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Five `Chapter*` schemas

**Files:**
- Modify: `src/services/chat/schemas/output.py`, `src/services/chat/schemas/__init__.py`
- Test: `src/services/chat/tests/test_structured_output_gate.py` (import smoke)

- [ ] **Step 1: Write the failing test** (append)

```python
def test_chapter_schemas_importable_from_package():
    from src.services.chat.schemas import (
        ChapterParse, ChapterResolveMatches, ChapterMapBlock,
        ChapterStitchOut, ChapterGroundOut,
    )
    assert ChapterParse().book_slug == ""
    assert ChapterResolveMatches().matches == []
    assert ChapterMapBlock().math_blocks == []
    assert ChapterStitchOut().intro == ""
    assert ChapterGroundOut().confidence == 0.5
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_structured_output_gate.py -q -k chapter_schemas`
Expected: FAIL — `ImportError: cannot import name 'ChapterParse'`.

- [ ] **Step 3: Implement — append to `src/services/chat/schemas/output.py`**

(The file already has `from pydantic import BaseModel, Field`.)

```python
class ChapterParse(BaseModel):
    """Shape of the chapter PARSE stage output (book/chapter scope)."""

    book_slug: str = ""
    book_confidence: float = 0.0
    book_candidates: list[str] = Field(default_factory=list)
    chapter_id: str = ""
    requested_subtopics: list[str] = Field(default_factory=list)


class ChapterResolveMatches(BaseModel):
    """Shape of the chapter RESOLVE stage output (subtopic -> heading)."""

    matches: list[dict] = Field(default_factory=list)


class ChapterMapBlock(BaseModel):
    """Shape of the chapter MAP stage output (one section block)."""

    body: str = ""
    citations: list[dict] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)


class ChapterStitchOut(BaseModel):
    """Shape of the chapter STITCH stage output (intro/outro)."""

    intro: str = ""
    outro: str = ""


class ChapterGroundOut(BaseModel):
    """Shape of the chapter GROUND stage output (grounding audit)."""

    ok: bool = False
    unsupported: list[str] = Field(default_factory=list)
    confidence: float = 0.5
```

- [ ] **Step 4: Export from `src/services/chat/schemas/__init__.py`**

Add the five names to the existing `from .output import (...)` block AND to `__all__`, following the existing style (look at how `FacilitateMap`/`FacilitateVerify` are listed and copy that pattern exactly).

- [ ] **Step 5: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_structured_output_gate.py -q -k chapter_schemas`
Expected: PASS. Also: `.venv/bin/python -c "from src.services.chat.schemas import ChapterParse, ChapterResolveMatches, ChapterMapBlock, ChapterStitchOut, ChapterGroundOut; print('ok')"` → `ok`.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/schemas/__init__.py src/services/chat/tests/test_structured_output_gate.py
git commit -m "feat(schemas): Chapter{Parse,ResolveMatches,MapBlock,StitchOut,GroundOut}

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: XML-scaffold the 5 chapter prompts

**Files:**
- Modify: `src/services/chat/prompts/chapter.py`
- Test: `src/services/chat/tests/test_t18_xml_scaffolds.py`

- [ ] **Step 1: Write the failing test** (append to `test_t18_xml_scaffolds.py`)

```python
_CHAPTER_PROMPTS = [
    "CHAPTER_PARSE_PROMPT",
    "CHAPTER_RESOLVE_PROMPT",
    "CHAPTER_MAP_RESUME_PROMPT",
    "CHAPTER_STITCH_PROMPT",
    "CHAPTER_GROUND_PROMPT",
]


@pytest.mark.parametrize("name", _CHAPTER_PROMPTS)
def test_chapter_prompt_has_xml_scaffold(name):
    mod = importlib.import_module("src.services.chat.prompts.chapter")
    text = getattr(mod, name)
    assert "<role>" in text and "</role>" in text, f"{name}: missing <role>"
    assert "<task>" in text and "</task>" in text, f"{name}: missing <task>"
    assert "<output_format>" in text and "</output_format>" in text, (
        f"{name}: missing <output_format>"
    )
    for legacy in ("ROLE:", "TASK:", "OUTPUT FORMAT"):
        assert legacy not in text, f"{name}: legacy '{legacy}' label present"
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_t18_xml_scaffolds.py -q -k chapter_prompt_has_xml`
Expected: FAIL — prompts lack `<role>` etc.

- [ ] **Step 3: Implement — rewrite the 5 prompts in `src/services/chat/prompts/chapter.py`**

For EACH prompt, keep the exact instruction text but wrap the natural sections in
`<role>`, `<task>`, `<output_format>`. The opening sentence ("You extract…",
"You map…", "You COMPRESS…", "You write…", "You audit…") becomes `<role>`. The
"You are given …" + return-instruction becomes `<task>` + `<output_format>`.
Concretely:

`CHAPTER_PARSE_PROMPT`:
```python
CHAPTER_PARSE_PROMPT = """<role>
You extract the study scope from a request and match it to a known book.
</role>

<task>
You are given:
  "catalog": array of {"slug","name","authors_short","field","chapters"} —
      the ONLY books available. "chapters" are valid chapter ids like "ch07".
  "selected_slugs": slugs the user already selected (may be empty).
  "message": the user's request.

Match the book the user means even when the title is paraphrased, partial, or
only the author is named (e.g. "Hansen's intro to probability"). Use meaning,
author surname, and field — not exact strings.
</task>

<output_format>
Return ONLY a JSON object with these keys:
  "book_slug": the single best slug, or "" if no catalog book is a plausible match.
  "book_confidence": 0..1 — how sure you are of book_slug.
  "book_candidates": array of slugs (best first) that plausibly match; one entry
      when confident, several when ambiguous, [] when nothing matches.
  "chapter_id": the chapter normalised as "chNN" (zero-padded). "" if none named.
  "requested_subtopics": array of the verbatim subtopic phrases the user named
      (NOT section numbers — those are handled separately). [] = whole chapter.

If exactly one slug is in selected_slugs, prefer it with high confidence.
Never invent a slug or chapter id that is not in the catalog.
</output_format>
"""
```

`CHAPTER_RESOLVE_PROMPT`:
```python
CHAPTER_RESOLVE_PROMPT = """<role>
You map a user's requested subtopics to a chapter's real section headings
(closest-match).
</role>

<task>
You are given:
  "requested": array of the phrases the user asked for.
  "headings": array of {"section_id": "...", "h2_path": "..."} — the chapter's
      actual sections, in order.

For EACH requested phrase, pick the single closest heading by meaning.
</task>

<output_format>
Return ONLY a JSON object:
  "matches": array of {"asked": "...", "section_id": "...",
      "matched_h2": "...", "score": 0..1} — score is your match confidence.
      If nothing is a reasonable match, set section_id="" matched_h2="" score=0.

Never invent a section_id that is not in "headings".
</output_format>
"""
```

`CHAPTER_MAP_RESUME_PROMPT`:
```python
CHAPTER_MAP_RESUME_PROMPT = """<role>
You COMPRESS one subtopic of a textbook chapter into a terse recap, grounded
ONLY in the provided section text.
</role>

<task>
You are given the section text, its heading, and a short "prior_context".
</task>

<output_format>
Return ONLY a JSON object:
  "body": markdown — a tight summary (roughly 40-100 words): the key
      definition(s), result(s), and any formula, as compact bullets or one
      dense paragraph. No teaching, no analogies, no padding. Cite with inline
      [n] markers.
  "citations": array of {"index": n, "chunkId": "...", "book_name": "...",
      "authors_short": "...", "year": int|null, "chapter": "...",
      "section": "...", "quote": "the exact supporting sentence"}.
  "math_blocks": array of LaTeX strings (may be empty).

Stay strictly within this section's content. Preserve order.
</output_format>
"""
```

`CHAPTER_STITCH_PROMPT`:
```python
CHAPTER_STITCH_PROMPT = """<role>
You write a short intro and outro for an ordered chapter digest.
</role>

<task>
You are given the ordered list of subtopic headings covered.
</task>

<output_format>
Return ONLY a JSON object:
  "intro": one or two sentences naming what this digest covers, in order.
  "outro": one sentence on how the pieces fit together.

Do not add new facts or reorder anything. Keep both very short.
</output_format>
"""
```

`CHAPTER_GROUND_PROMPT`:
```python
CHAPTER_GROUND_PROMPT = """<role>
You audit an assembled chapter digest against its sources.
</role>

<task>
You are given the concatenated body text and the numbered sources.
</task>

<output_format>
Return ONLY a JSON object:
  "ok": boolean — true if every claim is supported by some source.
  "unsupported": array of strings — claims not found in the sources.
  "confidence": number 0..1 — confidence the digest is fully grounded.

Do not rewrite the digest. Only report.
</output_format>
"""
```

(Leave `CHAPTER_MAP_FACILITATE_PROMPT` as-is — it is unused by resume and not in scope.)

- [ ] **Step 4: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_t18_xml_scaffolds.py -q`
Expected: PASS (chapter + existing facilitate/tutor scaffold tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/prompts/chapter.py src/services/chat/tests/test_t18_xml_scaffolds.py
git commit -m "refactor(chapter): XML-scaffold the 5 chapter prompts (parse/resolve/map/stitch/ground)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Gate `chapter.py` stages

**Files:**
- Modify: `src/services/chat/agents/chapter.py`
- Test: `src/services/chat/tests/test_chapter_gate.py` (new)

- [ ] **Step 1: Write the failing test** — create `src/services/chat/tests/test_chapter_gate.py`

```python
"""Structured-output gate wired into chapter.py stages."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.agents import chapter as ch


def _resp(content="{}"):
    class _Resp:
        class _Choice:
            class _Msg:
                pass
            message = _Msg()
        choices = [_Choice()]
    r = _Resp()
    r.choices[0].message.content = content
    return r


@pytest.mark.asyncio
async def test_chat_object_model_injects_response_format_token():
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return _resp("{}")

    client = AsyncMock()
    client.chat.completions.create = _create
    from src.services.chat.schemas import ChapterStitchOut
    with patch.object(ch, "aclient_for", return_value=client):
        await ch._chat(
            [{"role": "system", "content": "BASE"},
             {"role": "user", "content": "u"}],
            model="deepseek-v4-pro", max_tokens=100, schema=ChapterStitchOut,
        )
    assert captured["response_format"] == {"type": "json_object"}
    assert "<response_format>" in captured["messages"][0]["content"]
    assert "BASE" in captured["messages"][0]["content"]


@pytest.mark.asyncio
async def test_chat_schema_model_native_and_untouched():
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return _resp("{}")

    client = AsyncMock()
    client.chat.completions.create = _create
    from src.services.chat.schemas import ChapterStitchOut
    with patch.object(ch, "aclient_for", return_value=client):
        await ch._chat(
            [{"role": "system", "content": "BASE"}],
            model="gpt-4o", max_tokens=100, schema=ChapterStitchOut,
        )
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["messages"][0]["content"] == "BASE"


@pytest.mark.asyncio
async def test_stages_pass_their_schema():
    """map_sections/stitch/ground/resolve_subtopics each pass a schema to _chat."""
    from src.services.chat.schemas import (
        ChapterGroundOut, ChapterMapBlock, ChapterResolveMatches, ChapterStitchOut,
    )
    from src.services.chat.schemas import Source, ChapterBlock

    seen: list = []

    async def _spy(messages, *, model, max_tokens, temperature=0.0, schema=None):
        seen.append(schema)
        # Return minimal valid JSON for each caller.
        return '{"body":"x","citations":[],"math_blocks":[],"intro":"i","outro":"o",' \
               '"ok":true,"unsupported":[],"confidence":1.0,"matches":[]}'

    src = Source(chunkId="s1", book="b", book_name="B", chapter="ch01",
                 section="1.1", title="T", excerpt="e", chunk="c",
                 page_from=1, page_to=2, score=1.0)
    blk = ChapterBlock(h2_path="T", section_id="s1", body="b", page_from=1, page_to=2)
    with patch.object(ch, "_chat", _spy):
        await ch.map_sections([src], mode="resume", model="gpt-4o")
        await ch.stitch([blk], model="gpt-4o")
        await ch.ground([blk], [src], model="gpt-4o")
        await ch.resolve_subtopics(["x"], [src], model="gpt-4o")
    assert ChapterMapBlock in seen
    assert ChapterStitchOut in seen
    assert ChapterGroundOut in seen
    assert ChapterResolveMatches in seen
```

NOTE on the `Source`/`ChapterBlock` constructor fields: before writing this
test, open `src/services/chat/schemas/` and confirm the exact required fields and
construct them accordingly (the field set above is illustrative — match the real
models; if a field is required and missing the test will error, so adjust).

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_chapter_gate.py -q`
Expected: FAIL — `_chat() got an unexpected keyword argument 'schema'`.

- [ ] **Step 3: Implement the `_chat` gate in `src/services/chat/agents/chapter.py`**

Add import near the other `from src.services.chat.llm...` import:
```python
from src.services.chat.llm.structured import apply_structured_output
```
Add schema imports to the existing `from src.services.chat.schemas import (...)` block:
```python
    ChapterGroundOut,
    ChapterMapBlock,
    ChapterResolveMatches,
    ChapterStitchOut,
```
Replace `_chat` (lines 65-74) with:
```python
async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    """Single LLM seam. Returns the raw assistant content string."""
    oa = aclient_for(model)
    messages, response_format = apply_structured_output(messages, model, schema)
    kwargs: dict = {
        "model": model, "messages": messages,
        "temperature": temperature, "max_completion_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = await oa.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
```

- [ ] **Step 4: Pass schema at the four call sites**

- `resolve_subtopics` (the `_chat([... CHAPTER_RESOLVE_PROMPT ...], model=..., max_tokens=400)` call) → add `schema=ChapterResolveMatches`.
- `map_sections` (the `_chat([... sys_prompt ...], model=chosen, max_tokens=900)` call) → add `schema=ChapterMapBlock`.
- `stitch` (the `_chat([... CHAPTER_STITCH_PROMPT ...], max_tokens=200)` call) → add `schema=ChapterStitchOut`.
- `ground` (the `_chat([... CHAPTER_GROUND_PROMPT ...], max_tokens=500)` call) → add `schema=ChapterGroundOut`.

- [ ] **Step 5: Run, verify PASS + no chapter regressions**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_chapter_gate.py src/services/chat/tests/ -q -k "chapter or facilitate or structured"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/chapter.py src/services/chat/tests/test_chapter_gate.py
git commit -m "feat(chapter): gate resolve/map/stitch/ground via apply_structured_output

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Gate `_scope.py` parse + retrofit `facilitate.py`

**Files:**
- Modify: `src/services/chat/agents/_scope.py`, `src/services/chat/agents/facilitate.py`
- Test: `src/services/chat/tests/test_scope_gate.py` (new)

- [ ] **Step 1: Write the failing test** — create `src/services/chat/tests/test_scope_gate.py`

```python
"""Structured-output gate wired into _scope.resolve_book (PARSE stage)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.agents import _scope
from src.services.chat.schemas import CatalogBook


def _resp(content):
    class _Resp:
        class _Choice:
            class _Msg:
                pass
            message = _Msg()
        choices = [_Choice()]
    r = _Resp()
    r.choices[0].message.content = content
    return r


def _catalog():
    return [CatalogBook(slug="hansen", name="Probability", authors_short="Hansen",
                        field="stats", chapters=["ch01"])]


@pytest.mark.asyncio
async def test_resolve_book_object_model_injects_token():
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return _resp('{"book_slug":"hansen","book_confidence":0.9,'
                     '"book_candidates":["hansen"],"chapter_id":"ch01",'
                     '"requested_subtopics":[]}')

    client = AsyncMock()
    client.chat.completions.create = _create
    with patch.object(_scope, "aclient_for", return_value=client):
        res = await _scope.resolve_book(
            "hansen ch1", selected_slugs=None, catalog=_catalog(),
            model="deepseek-v4-pro")
    assert res.book_slug == "hansen"
    assert captured["response_format"] == {"type": "json_object"}
    sys_msg = captured["messages"][0]["content"]
    assert "<response_format>" in sys_msg


@pytest.mark.asyncio
async def test_resolve_book_schema_model_native():
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return _resp('{"book_slug":"hansen","book_confidence":0.9,'
                     '"book_candidates":["hansen"],"chapter_id":"ch01",'
                     '"requested_subtopics":[]}')

    client = AsyncMock()
    client.chat.completions.create = _create
    with patch.object(_scope, "aclient_for", return_value=client):
        await _scope.resolve_book(
            "hansen ch1", selected_slugs=None, catalog=_catalog(), model="gpt-4o")
    assert captured["response_format"]["type"] == "json_schema"
    # parse system message is the CHAPTER_PARSE_PROMPT, no token appended
    assert "<response_format>" not in captured["messages"][0]["content"]
```

NOTE: confirm `CatalogBook`'s exact fields before writing (open `schemas/`); the
field set above matches `_catalog_payload`/`_candidate_records` usage but verify.

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_scope_gate.py -q`
Expected: FAIL — `_chat() got an unexpected keyword argument 'schema'`.

- [ ] **Step 3: Implement `_scope.py`**

Add imports:
```python
from src.services.chat.llm.structured import apply_structured_output  # noqa: E402
from src.services.chat.schemas import ChapterParse  # noqa: E402
```
(Place near the existing `from src.services.chat.prompts.chapter import CHAPTER_PARSE_PROMPT` line / `from src.services.chat.schemas import ...` line, respecting the file's E402 pattern.)

Replace `_chat` (lines 61-68) with:
```python
async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    """Single LLM seam (tests monkeypatch this)."""
    oa = aclient_for(model)
    messages, response_format = apply_structured_output(messages, model, schema)
    kwargs: dict = {
        "model": model, "messages": messages,
        "temperature": temperature, "max_completion_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = await oa.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
```
In `resolve_book`, add `schema=ChapterParse` to its `_chat(...)` call.

- [ ] **Step 4: Retrofit `facilitate.py` `_chat` to use the helper**

In `src/services/chat/agents/facilitate.py`, replace the imports/usage: change
```python
from src.services.chat.llm.structured import resolve_response_format
```
to
```python
from src.services.chat.llm.structured import apply_structured_output
```
and replace the body of `_chat` (the resolve + manual loop) with:
```python
async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    oa = aclient_for(model)
    messages, response_format = apply_structured_output(messages, model, schema)
    kwargs: dict = {
        "model": model, "messages": messages,
        "temperature": temperature, "max_completion_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = await oa.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
```
(MAP/VERIFY call sites already pass `schema=`; leave them.)

- [ ] **Step 5: Run, verify PASS + full sweep**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_scope_gate.py src/services/chat/tests/ -q`
Expected: PASS. Existing facilitate tests still pass — their assertions check
that the system message contains "json" and the schema keys, which the
`<response_format>` token still includes. If a facilitate test asserted the hint
was NOT wrapped, update it to assert the token is present (do not weaken the
intent).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/_scope.py src/services/chat/agents/facilitate.py src/services/chat/tests/test_scope_gate.py
git commit -m "feat(scope): gate PARSE via apply_structured_output; facilitate retrofit to shared helper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- `<response_format>` token in `_schema_hint` → Task 1. ✔
- `apply_structured_output` centralization → Task 1; used in Tasks 4 & 5. ✔
- Retrofit facilitate + tutor to token: facilitate → Task 5; tutor uses `schema_hint` which now wraps → automatic (covered by Task 1; tutor's existing test asserts "json" in prompt, still true). ✔
- Five Chapter* schemas + exports → Task 2. ✔
- XML-scaffold all 5 chapter prompts → Task 3. ✔
- Gate chapter stages (map/stitch/ground/resolve) → Task 4. ✔
- Gate parse via _scope → Task 5. ✔
- Tests for token, apply helper, chapter gate, scope gate, prompt scaffold → Tasks 1,3,4,5. ✔
- qa shared-parse upgrade noted → Task 5 covers _scope (shared). ✔

**Placeholder scan:** none. Two NOTEs ask the implementer to verify real
`Source`/`ChapterBlock`/`CatalogBook` fields before constructing — this is a
deliberate guard, not a placeholder (the test code is complete; the note prevents
a wrong-field error).

**Type consistency:** `apply_structured_output(messages, model_id, schema) ->
(list[dict], dict|None)` used identically in chapter.py, _scope.py, facilitate.py.
Schema names `ChapterParse / ChapterResolveMatches / ChapterMapBlock /
ChapterStitchOut / ChapterGroundOut` consistent across Tasks 2, 4, 5. `_chat`
signature `(messages, *, model, max_tokens, temperature=0.0, schema=None)`
identical across all three seams.

**Tutor note:** tutor is NOT re-touched here; it already calls `schema_hint`,
which Task 1 changes to emit the token, so tutor's fallback prompt automatically
gains `<response_format>`. Its test asserts `"json" in system_prompt.lower()` —
still true.
