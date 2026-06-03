# QA Prompt Standardization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Q&A mode match the project's structured-output convention — XML-scaffolded prompts + every LLM call routed through the `apply_structured_output` capability gate — with zero change to QA's pipeline, SSE contract, or fail-open behaviour.

**Architecture:** Three additive, isolated changes: (1) add two per-call pydantic schemas; (2) rewrite the three QA prompt constants into the `<role>/<task>/<output_format>/<rules>` scaffold, content verbatim; (3) replace QA's `_chat` seam with the facilitate/chapter version (takes a `schema`, calls the gate, threads `response_format`) and pass each stage's schema. Existing `strip_fences`/`json.loads`/retry/fail-open stays untouched.

**Tech Stack:** Python 3.12, pydantic, pytest (`.venv/bin/python -m pytest`), OpenAI-compat async client.

---

## File Structure

- `src/services/chat/schemas/output.py` — add `QAGenerateOut`, `QAVerifyOut` (next to `QAAnswer`).
- `src/services/chat/schemas/__init__.py` — export the two new models.
- `src/services/chat/prompts/qa.py` — scaffold the 3 prompt constants + docstring.
- `src/services/chat/agents/qa.py` — gate-wire `_chat`; pass schema at 3 call sites.
- `src/services/chat/tests/test_qa_schemas.py` — new: schema existence/shape.
- `src/services/chat/tests/test_qa_xml_scaffold.py` — new: scaffold guard.
- `src/services/chat/tests/test_qa_gate.py` — new: gate wiring (mirrors `test_chapter_gate.py`).
- `docs/services/chat-features/51-qa-mode.md`, `docs/system/changelog.md`, `docs/system/invariants.md` — doc notes.

All test commands assume CWD `/home/iohan/Documents/toolbox/AI_models/RAG` and run with a memory cap:
`ulimit -v 6291456` prefix is optional but matches house style.

---

## Task 1: QA per-call schemas

**Files:**
- Test: `src/services/chat/tests/test_qa_schemas.py` (create)
- Modify: `src/services/chat/schemas/output.py` (add after the `QAAnswer` class, before the `Mode 3/4 — chapter` divider comment)
- Modify: `src/services/chat/schemas/__init__.py` (add to the import block and `__all__`)

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_qa_schemas.py`:

```python
"""QA per-call output schemas exist and have the expected shape."""
from __future__ import annotations


def test_qa_generate_out_shape():
    from src.services.chat.schemas import QAGenerateOut, TutorCitation

    m = QAGenerateOut()
    assert m.text == ""
    assert m.citations == []
    assert m.math_blocks == []
    # citations are TutorCitation instances when populated
    c = TutorCitation(index=1, chunkId="x", authors_short="A", year=None,
                      book_name="B", chapter="ch01", section="1.1", quote="q")
    m2 = QAGenerateOut(text="t", citations=[c], math_blocks=["E=mc^2"])
    assert m2.citations[0].index == 1
    # json schema is extractable (used by the structured-output gate)
    assert "properties" in QAGenerateOut.model_json_schema()


def test_qa_verify_out_shape():
    from src.services.chat.schemas import QAVerifyOut

    m = QAVerifyOut()
    assert m.ok is False
    assert m.unsupported == []
    assert m.confidence == 0.5
    assert m.text == ""
    assert "properties" in QAVerifyOut.model_json_schema()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'QAGenerateOut'`.

- [ ] **Step 3: Add the schemas**

In `src/services/chat/schemas/output.py`, immediately after the `QAAnswer` class
body and before the line:

```python
# ---------------------------------------------------------------------------
# Mode 3/4 — chapter (facilitate + resume)
# ---------------------------------------------------------------------------
```

insert:

```python
class QAGenerateOut(BaseModel):
    """Raw output of QA_GENERATE_PROMPT (the generate node).

    Describes the shape for the structured-output gate; the agent still parses
    defensively and maps the result into :class:`QAAnswer`.
    """

    text: str = ""
    citations: list[TutorCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)


class QAVerifyOut(BaseModel):
    """Raw output of QA_VERIFY_PROMPT (the advisory grounding audit)."""

    ok: bool = False
    unsupported: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    text: str = ""
```

(`BaseModel`, `Field`, and `TutorCitation` are already imported/defined in this module.)

- [ ] **Step 4: Export from the package**

In `src/services/chat/schemas/__init__.py`, add `QAGenerateOut,` and
`QAVerifyOut,` to the import block right after the existing `QAAnswer,` line
(currently line 41), and add `"QAGenerateOut",` and `"QAVerifyOut",` to `__all__`
right after the existing `"QAAnswer",` line (currently line 89).

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_schemas.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/schemas/__init__.py src/services/chat/tests/test_qa_schemas.py
git commit -m "feat(schemas): QAGenerateOut + QAVerifyOut per-call QA schemas"
```

---

## Task 2: XML-scaffold the QA prompts

**Files:**
- Test: `src/services/chat/tests/test_qa_xml_scaffold.py` (create)
- Modify: `src/services/chat/prompts/qa.py` (rewrite the 3 constants + docstring)

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_qa_xml_scaffold.py`:

```python
"""QA prompts use the <role>/<task>/<output_format>/<rules> scaffold."""
from __future__ import annotations

import pytest

from src.services.chat.prompts import qa

PROMPTS = ["QA_SCOPE_PROMPT", "QA_GENERATE_PROMPT", "QA_VERIFY_PROMPT"]
TAGS = ["role", "task", "output_format", "rules"]


@pytest.mark.parametrize("name", PROMPTS)
def test_prompt_opens_with_role(name):
    text = getattr(qa, name)
    assert text.lstrip().startswith("<role>"), f"{name}: must open with <role>"


@pytest.mark.parametrize("name", PROMPTS)
@pytest.mark.parametrize("tag", TAGS)
def test_prompt_has_all_scaffold_tags(name, tag):
    text = getattr(qa, name)
    assert f"<{tag}>" in text and f"</{tag}>" in text, (
        f"{name}: missing <{tag}>...</{tag}>"
    )


@pytest.mark.parametrize("name", PROMPTS)
def test_json_instruction_lives_inside_output_format(name):
    """The 'Return ONLY a JSON object' instruction must sit in <output_format>,
    not float as a bare legacy label."""
    text = getattr(qa, name)
    if "Return ONLY a JSON object" not in text:
        return  # scope prompt may phrase it differently; only guard when present
    before = text.split("<output_format>", 1)[0]
    assert "Return ONLY a JSON object" not in before, (
        f"{name}: JSON instruction leaked outside <output_format>"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_xml_scaffold.py -v`
Expected: FAIL — current prompts have no `<role>` tag.

- [ ] **Step 3: Rewrite `prompts/qa.py`**

Replace the entire file `src/services/chat/prompts/qa.py` with:

```python
"""Prompts for the punctual Q&A mode.

Three single-purpose system prompts: scope extraction, scoped generation, and
grounding verification. All are XML-scaffolded
(<role>/<task>/<output_format>/<rules>) — same convention as the tutor and
chapter prompts. Kept terse: Q&A is a short, direct pipeline.

Chinese-wall: pure string constants, no imports from src.*.
"""
from __future__ import annotations

QA_SCOPE_PROMPT = """<role>
You parse a student's question into its precise scope.
</role>

<task>
The input is the student's question.
</task>

<output_format>
Return ONLY a JSON object with exactly these keys:
  "target_gap": string — the single specific thing the student wants answered.
  "assumed_known": array of strings — concepts the student SIGNALS they already
      understand (e.g. "I know what X is"). Empty array if none signalled.
  "answer_form": one of "explanation","definition","comparison","derivation",
      "yes_no","list" — the natural shape of the answer.

Example input: "What is the bias-variance tradeoff? I know what the elements
are, except the tradeoff."
Example output:
{"target_gap":"why bias and variance trade off against each other",
"assumed_known":["what bias is","what variance is"],
"answer_form":"explanation"}
</output_format>

<rules>
- Extract assumed_known ONLY from explicit signals ("I know…", "except…",
  "I understand…"). Do not invent.
- target_gap must be the narrowed question, not the whole topic.
</rules>
"""

QA_GENERATE_PROMPT = """<role>
You answer ONE specific question directly and briefly, grounded ONLY in the
provided textbook sources.
</role>

<task>
You are given:
- target_gap: the exact thing to answer.
- assumed_known: things the student ALREADY knows — you MUST NOT explain,
  define, or re-derive these. Skip them entirely.
- sources: numbered textbook passages.
</task>

<output_format>
Return ONLY a JSON object:
  "text": markdown answering target_gap and nothing else. Be punctual: no
      preamble, no scaffolding, no examples unless answer_form is "list" or the
      question asks for one, no restating assumed_known. Cite claims with inline
      [n] markers referencing the source numbers you used.
  "citations": array of {"index": n, "chunkId": "...", "book_name": "...",
      "authors_short": "...", "year": int|null, "chapter": "...",
      "section": "...", "quote": "the exact supporting sentence"} — one per
      [n] marker you used.
  "math_blocks": array of LaTeX strings for any display equations (may be empty).
</output_format>

<rules>
If the sources do not contain the answer, set text to a one-sentence honest
statement that the selected books do not cover it, and citations to [].
</rules>
"""

QA_VERIFY_PROMPT = """<role>
You audit a drafted answer against its sources.
</role>

<task>
You are given the draft "text" and the numbered "sources". Check every factual
claim in the draft is supported by at least one source.
</task>

<output_format>
Return ONLY a JSON object:
  "ok": boolean — true if every claim is supported.
  "unsupported": array of strings — claims NOT found in the sources (empty if ok).
  "confidence": number 0..1 — your confidence the answer is fully grounded.
  "text": the draft text with any unsupported sentence removed or softened;
      return the draft unchanged when ok is true.
</output_format>

<rules>
Do not add new facts. Only remove/soften unsupported ones.
</rules>
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_xml_scaffold.py -v`
Expected: PASS.

- [ ] **Step 5: Confirm QA agent tests still pass (prompts are imported there)**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -k qa -q`
Expected: PASS (existing QA tests unaffected — prompt content preserved).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/prompts/qa.py src/services/chat/tests/test_qa_xml_scaffold.py
git commit -m "refactor(qa): XML-scaffold the 3 Q&A prompts (content verbatim)"
```

---

## Task 3: Wire the structured-output gate into `agents/qa.py`

**Files:**
- Test: `src/services/chat/tests/test_qa_gate.py` (create)
- Modify: `src/services/chat/agents/qa.py` (import + `_chat` + 3 call sites)

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_qa_gate.py` (mirrors `test_chapter_gate.py`):

```python
"""Structured-output gate wired into qa.py stages."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.agents import qa


def _resp(content="{}"):
    class _Msg: ...
    class _Choice: ...
    class _Resp: ...
    msg = _Msg(); msg.content = content
    choice = _Choice(); choice.message = msg
    r = _Resp(); r.choices = [choice]
    return r


@pytest.mark.asyncio
async def test_chat_object_model_injects_response_format_token():
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return _resp("{}")

    client = AsyncMock()
    client.chat.completions.create = _create
    from src.services.chat.schemas import QAVerifyOut
    with patch.object(qa, "aclient_for", return_value=client):
        await qa._chat(
            [{"role": "system", "content": "BASE"},
             {"role": "user", "content": "u"}],
            model="deepseek-v4-pro", max_tokens=100, schema=QAVerifyOut,
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
    from src.services.chat.schemas import QAVerifyOut
    with patch.object(qa, "aclient_for", return_value=client):
        await qa._chat(
            [{"role": "system", "content": "BASE"}],
            model="gpt-4o", max_tokens=100, schema=QAVerifyOut,
        )
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["messages"][0]["content"] == "BASE"


@pytest.mark.asyncio
async def test_stages_pass_their_schema():
    """extract_scope / generate_scoped / verify_grounding each hand _chat a schema."""
    from src.services.chat.schemas import (
        QAScope, QAGenerateOut, QAVerifyOut, Source,
    )
    seen = []

    async def _spy(messages, *, model, max_tokens, temperature=0.0, schema=None):
        seen.append(schema)
        return ('{"target_gap":"g","assumed_known":[],"answer_form":"explanation",'
                '"text":"t","citations":[],"math_blocks":[],'
                '"ok":true,"unsupported":[],"confidence":1.0}')

    src = Source(
        rank=1, book="b", chapter="ch01", section="1.1", title="Alpha",
        excerpt="ex", score=0.9, chunkId="c1", chunk="full chunk",
    )
    scope = QAScope(target_gap="g")

    with patch.object(qa, "_chat", _spy):
        await qa.extract_scope("question?", model="gpt-4o")
        await qa.generate_scoped(scope, [src], model="gpt-4o")
        await qa.verify_grounding(
            qa.QAAnswer(text="t", scope=scope), [src], model="gpt-4o"
        )

    assert QAScope in seen
    assert QAGenerateOut in seen
    assert QAVerifyOut in seen
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_gate.py -v`
Expected: FAIL — `_chat` has no `schema` param / `response_format` not set
(`TypeError` or `KeyError: 'response_format'`).

- [ ] **Step 3: Add the gate import**

In `src/services/chat/agents/qa.py`, in the import block, add after the existing
`from src.services.chat.llm.router import aclient_for` line:

```python
from src.services.chat.llm.structured import apply_structured_output
```

Also extend the `schemas` import line to bring in the two new models. Change:

```python
from src.services.chat.schemas import ChatRequest, QAAnswer, QAScope, Source, TutorCitation
```

to:

```python
from src.services.chat.schemas import (
    ChatRequest, QAAnswer, QAGenerateOut, QAScope, QAVerifyOut, Source, TutorCitation,
)
```

- [ ] **Step 4: Replace `_chat`**

Replace the existing `_chat` function with the gated version:

```python
async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    """Single LLM seam. Returns the raw assistant content string.

    Routes through the per-model structured-output gate: json_schema when the
    model supports it, else json_object + a <response_format> hint appended to
    the system message. Parsing stays defensive downstream (strip_fences +
    json.loads), so json_object-only providers are still handled.
    """
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

- [ ] **Step 5: Pass the schema at each call site**

In `extract_scope`, the `_chat(...)` call — add `schema=QAScope`:

```python
        raw = await _chat(
            [
                {"role": "system", "content": QA_SCOPE_PROMPT},
                {"role": "user", "content": query},
            ],
            model=chosen,
            max_tokens=200,
            schema=QAScope,
        )
```

In `generate_scoped`, the inner `_one()` helper — add `schema=QAGenerateOut`:

```python
    async def _one() -> dict:
        raw = await _chat(messages, model=chosen, max_tokens=900, schema=QAGenerateOut)
        return json.loads(strip_fences(raw))
```

In `verify_grounding`, the `_chat(...)` call — add `schema=QAVerifyOut`:

```python
        raw = await _chat(
            [
                {"role": "system", "content": QA_VERIFY_PROMPT},
                {"role": "user", "content": user},
            ],
            model=chosen,
            max_tokens=700,
            schema=QAVerifyOut,
        )
```

- [ ] **Step 6: Run the gate test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_gate.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Run all QA tests (no regressions)**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -k qa -q`
Expected: PASS — existing fail-open/scope/generate/verify tests unaffected.

- [ ] **Step 8: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_gate.py
git commit -m "feat(qa): route scope/generate/verify through structured-output gate"
```

---

## Task 4: Docs (interconnected-artifact rule)

**Files:**
- Modify: `docs/services/chat-features/51-qa-mode.md`
- Modify: `docs/system/changelog.md`
- Modify: `docs/system/invariants.md`

- [ ] **Step 1: Update the QA feature doc**

In `docs/services/chat-features/51-qa-mode.md`, add a short note (a sentence or
two, in the prompts/pipeline section) stating: the three QA prompts are now
XML-scaffolded (`<role>/<task>/<output_format>/<rules>`) and all three LLM calls
(scope/generate/verify) run through `apply_structured_output` — json_schema when
the model supports it, else json_object plus a `<response_format>` hint — with
`QAScope` / `QAGenerateOut` / `QAVerifyOut` as the per-call schemas. Note the
SSE payload (`QAAnswer`) is unchanged.

- [ ] **Step 2: Add a changelog entry**

In `docs/system/changelog.md`, add a dated entry under the top/most-recent
section:

```markdown
- **QA prompt standardization** — Q&A mode prompts retrofitted to the
  `<role>/<task>/<output_format>/<rules>` scaffold and its scope/generate/verify
  LLM calls routed through the structured-output capability gate
  (`QAScope`/`QAGenerateOut`/`QAVerifyOut`). Additive only: pipeline, SSE
  contract, and fail-open behaviour unchanged.
```

- [ ] **Step 3: Extend the structured-output / prompt-format invariant**

In `docs/system/invariants.md`, find the invariant covering prompt scaffolding
and/or the structured-output gate and extend it to state that **all** live-mode
prompts (tutor, chapter, facilitate, **qa**) are XML-scaffolded and **all** mode
LLM calls pass through `apply_structured_output`. If no such invariant exists,
add one sentence to that effect in the prompts/structured-output section.

- [ ] **Step 4: Commit**

```bash
git add docs/services/chat-features/51-qa-mode.md docs/system/changelog.md docs/system/invariants.md
git commit -m "docs(qa): note prompt scaffold + structured-output gate (feature 51)"
```

---

## Final verification

- [ ] **Run the full chat test suite (default config excludes live quality tests):**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: all pass (3 groq skipped for missing key is fine).

- [ ] **Confirm no frontend impact** — no `web/` files were touched; the SSE
  `structured_output` event still carries `schema: "QAAnswer"`.

---

## Notes for the implementer

- **Why keep `strip_fences` + `json.loads` + retry?** The gate only guarantees
  schema-constrained decoding for `json_schema`-capable models. `json_object`-only
  providers (DeepSeek, some Groq) can still emit fences/preamble, so the defensive
  parse and the generate one-retry remain the safety net. Do not remove them.
- **The new schemas describe raw model output, not the SSE payload.** The agent
  continues to map into `QAAnswer` via `_coerce_citations` etc. `QAGenerateOut`/
  `QAVerifyOut` are passed to the gate only (same as chapter passes
  `ChapterMapBlock` while parsing manually).
- **`_chat` is intentionally duplicated per agent module** (facilitate/chapter/qa
  each define their own) so tests can monkeypatch one seam — do not extract a
  shared helper.
```
