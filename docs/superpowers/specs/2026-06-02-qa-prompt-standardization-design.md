# QA prompt standardization — XML scaffold + structured-output gate

**Date:** 2026-06-02
**Status:** approved (design)
**Scope:** Q&A mode only (`prompts/qa.py`, `agents/qa.py`, `schemas/output.py`).

## Problem

Q&A is the lone mode whose prompts and LLM calls do not follow the project's
established structured-output convention:

1. **Prompts** (`src/services/chat/prompts/qa.py`) use plain prose plus a bare
   "Return ONLY a JSON object" instruction. Every other mode (tutor, chapter,
   facilitate) uses the `<role>/<task>/<output_format>[/<rules>]` XML scaffold.
2. **No capability gate.** `agents/qa.py::_chat` calls
   `chat.completions.create()` directly and relies solely on
   `strip_fences` + `json.loads`. The sibling agents (`facilitate.py`,
   `chapter.py`, `_scope.py`) route every LLM call through
   `apply_structured_output(messages, model, schema)`, which selects
   `json_schema` vs `json_object` per model and, when schema-constrained
   decoding is unsupported, appends a compact schema hint inside a
   `<response_format>` token.

The goal is consistency, not new behaviour: make QA match the siblings exactly,
with no change to QA's pipeline, SSE contract, or fail-open semantics.

## Out of scope (YAGNI)

- Auditing or touching any other mode's prompts (tutor/chapter/facilitate/
  `_scope`/`image_judge` already conform).
- Any change to QA's pipeline shape (scope → retrieve → generate → verify),
  SSE events, or the `QAAnswer` payload the frontend consumes.
- Removing the existing `strip_fences` / `json.loads` / one-retry / fail-open
  paths — they stay as belt-and-suspenders for `json_object`-only providers.
- Modal card / `PipelineDiagram` changes — no stage is added or renamed.

## Design

### 1. Prompts — `src/services/chat/prompts/qa.py`

Convert the three prompts to the `<role>/<task>/<output_format>/<rules>`
scaffold, **preserving the instruction content verbatim** (same retrofit applied
to the FACILITATE_* and CHAPTER_* prompts):

- `QA_SCOPE_PROMPT`
  - `<role>`: parse a student's question into its precise scope.
  - `<task>`: the input is the student's question.
  - `<output_format>`: the JSON keys (`target_gap`, `assumed_known`,
    `answer_form`) and the worked example, verbatim.
  - `<rules>`: extract `assumed_known` only from explicit signals; `target_gap`
    is the narrowed question, not the whole topic.
- `QA_GENERATE_PROMPT`
  - `<role>`: answer ONE specific question, grounded only in the sources.
  - `<task>`: inputs are `target_gap`, `assumed_known`, `sources`.
  - `<output_format>`: the JSON object (`text`, `citations`, `math_blocks`)
    with the citation field spec, verbatim.
  - `<rules>`: be punctual; never explain `assumed_known`; corpus-miss honesty.
- `QA_VERIFY_PROMPT`
  - `<role>`: audit a drafted answer against its sources.
  - `<task>`: inputs are the draft `text` and numbered `sources`.
  - `<output_format>`: the JSON object (`ok`, `unsupported`, `confidence`,
    `text`), verbatim.
  - `<rules>`: do not add new facts; only remove/soften unsupported claims.

Update the module docstring to state the prompts are XML-scaffolded. No imports
added (Chinese-wall: pure string constants).

### 2. Schemas — `src/services/chat/schemas/output.py`

Add two per-call pydantic models (mirrors the chapter convention of one schema
per LLM call), and export them from the schemas package `__init__`:

```python
class QAGenerateOut(BaseModel):
    """What QA_GENERATE_PROMPT returns (mapped into QAAnswer by the agent)."""
    text: str
    citations: list[TutorCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)


class QAVerifyOut(BaseModel):
    """What QA_VERIFY_PROMPT returns (advisory grounding audit)."""
    ok: bool = False
    unsupported: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    text: str = ""
```

`QAScope` already exists and is used as the scope-stage schema. These models
describe the *raw model output*; the agent still maps them into the existing
`QAAnswer` (adding `scope` + `grounding`), so the public payload is unchanged.

### 3. Agent — `src/services/chat/agents/qa.py`

- Import `apply_structured_output` from `src.services.chat.llm.structured`.
- Change the `_chat` seam to mirror `facilitate.py::_chat` exactly:

  ```python
  async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
      oa = aclient_for(model)
      messages, response_format = apply_structured_output(messages, model, schema)
      kwargs = {"model": model, "messages": messages,
                "temperature": temperature, "max_completion_tokens": max_tokens}
      if response_format is not None:
          kwargs["response_format"] = response_format
      resp = await oa.chat.completions.create(**kwargs)
      return resp.choices[0].message.content or ""
  ```

- Pass the schema at each call site:
  - `extract_scope` → `schema=QAScope`
  - `generate_scoped` → `schema=QAGenerateOut`
  - `verify_grounding` → `schema=QAVerifyOut`
- Everything else (`strip_fences`, `json.loads`, the generate one-retry, all
  `except`/fail-open branches) stays byte-for-byte. The gate is purely additive.

### 4. Error handling

Unchanged. The gate only shapes the request; it never raises in a new place.
`json_object`-only providers can still emit fenced/preamble junk, so the
existing `strip_fences` + parse-retry + fail-open paths remain the safety net.

### 5. Tests — `src/services/chat/tests/`

- `test_qa_xml_scaffold.py` (new): for each of the three QA prompts, assert all
  four tags `<role>/<task>/<output_format>/<rules>` are present and that no bare
  legacy `"Return ONLY a JSON object"` string appears *outside* the
  `<output_format>` block. Mirrors the t18 facilitate scaffold guard.
- `test_qa_structured_gate.py` (new): assert QA `_chat` routes through the gate
  — a `gpt-*` model + schema yields a `json_schema` `response_format`; a
  `deepseek-*` model falls back to `json_object` and appends the
  `<response_format>` hint to the system message. Mirror the existing
  facilitate/chapter gate test.
- Existing QA agent tests (`extract_scope` / `generate_scoped` /
  `verify_grounding` fail-open) must stay green unchanged.

### 6. Docs (interconnected-artifact rule)

- `docs/services/chat-features/51-qa-mode.md`: note the prompts are now
  XML-scaffolded and the three calls run through the structured-output gate.
- `docs/system/changelog.md`: one entry.
- `docs/system/invariants.md`: extend the prompt-format / structured-output-gate
  invariant to include QA (all live-mode prompts scaffolded; all mode LLM calls
  gated).
- No modal / `PipelineDiagram` / SSE / frontend change — QA stages and payload
  are untouched.

## Success criteria

1. All three QA prompts carry the four scaffold tags; content unchanged in
   meaning.
2. The three QA LLM calls run through `apply_structured_output` with the correct
   schema, and pass `response_format` to the client when one is produced.
3. New scaffold + gate tests pass; all pre-existing QA tests still pass.
4. No change to QA's SSE events or the `QAAnswer` the frontend renders.
