# Resume Mode — XML Scaffold + Structured-Output Gate with `<response_format>` Token

**Date:** 2026-06-02
**Status:** Approved (brainstorm)
**Scope:** `resume` mode (and the chapter stages it shares with `facilitate`/`qa`)

## Problem

The `resume` mode runs through `agents/chapter.py::run_chapter` with five JSON-
producing LLM stages — parse, resolve, map, stitch, ground — driven by the
`CHAPTER_*` prompts in `prompts/chapter.py`. Those prompts are still in the old
free-prose style (no `<role>/<task>/<output_format>` scaffold), and none of the
stages use the structured-output capability gate added for tutor + facilitate.
So on object-only models (DeepSeek, Groq llama/gpt-oss) resume relies on
prompt-and-pray + `strip_fences`.

## Goal

Apply the same transformation already shipped for tutor + facilitate to resume:

1. **XML-scaffold** all 5 chapter prompts (`CHAPTER_PARSE_PROMPT`,
   `CHAPTER_RESOLVE_PROMPT`, `CHAPTER_MAP_RESUME_PROMPT`, `CHAPTER_STITCH_PROMPT`,
   `CHAPTER_GROUND_PROMPT`) into `<role>/<task>/<output_format>` tags, content
   preserved verbatim.
2. **Capability gate** each stage: native `json_schema` when supported, else
   `json_object` + a schema hint injected into the system message.
3. **`<response_format>` special token:** when `json_schema` is NOT allowed, the
   injected hint is wrapped in a dedicated `<response_format>…</response_format>`
   XML token (not a bare sentence). This makes the fallback an explicit,
   greppable contract. Facilitate + tutor are retrofitted to the same wrapped
   form so the "special token" is uniform across modes.

## Approach (chosen)

- **Single source for the token:** wrap the hint inside the existing
  `structured._schema_hint`, so `schema_hint`, `resolve_response_format`, and
  every caller emit `<response_format>…</response_format>` automatically.
- **Centralize injection:** add `apply_structured_output(messages, model, schema)`
  to `structured.py` (resolve + inject in one call). The three `_chat` seams
  (`facilitate.py`, `chapter.py`, `_scope.py`) all use it — removes the
  duplicated find-system-message loop.
- **Per-stage schemas:** five new Pydantic models describe the JSON shapes.

## Components

### 1. `src/services/chat/llm/structured.py`

- `_schema_hint(js)` now returns:
  ```
  <response_format>
  Return ONLY a valid json object with exactly these keys: <keys> (required: <req>).
  Shape: {<k>: "...", ...}
  </response_format>
  ```
  (Still contains the literal word "json" + the keys → satisfies DeepSeek/Qwen
  and all existing substring assertions.)
- New:
  ```python
  def apply_structured_output(
      messages: list[dict], model_id: str | None, schema: type | None,
  ) -> tuple[list[dict], dict | None]:
      """Resolve the response_format for *model_id*/*schema* and, when falling
      back, inject the <response_format> hint into the system message (copying
      the list; prepending a system message if none exists).

      Returns (possibly-new messages list, response_format payload or None).
      """
  ```
  `schema_hint` and `resolve_response_format` are unchanged in signature.

### 2. `src/services/chat/schemas/output.py` (+ `__init__.py` exports)

Five models matching the stages' parsed JSON:

```python
class ChapterParse(BaseModel):
    book_slug: str = ""
    book_confidence: float = 0.0
    book_candidates: list[str] = Field(default_factory=list)
    chapter_id: str = ""
    requested_subtopics: list[str] = Field(default_factory=list)

class ChapterResolveMatches(BaseModel):
    matches: list[dict] = Field(default_factory=list)

class ChapterMapBlock(BaseModel):
    body: str = ""
    citations: list[dict] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)

class ChapterStitchOut(BaseModel):
    intro: str = ""
    outro: str = ""

class ChapterGroundOut(BaseModel):
    ok: bool = False
    unsupported: list[str] = Field(default_factory=list)
    confidence: float = 0.5
```

### 3. `src/services/chat/prompts/chapter.py`

Convert the 5 prompts to `<role>/<task>/<output_format>` scaffold (mirror
tutor/facilitate). The JSON-shape description stays inside `<output_format>`,
verbatim. No wording changes — only the section delimiters.

### 4. `src/services/chat/agents/chapter.py`

- `_chat(messages, *, model, max_tokens, temperature=0.0, schema=None)`:
  ```python
  oa = aclient_for(model)
  messages, response_format = apply_structured_output(messages, model, schema)
  kwargs = {"model": model, "messages": messages,
            "temperature": temperature, "max_completion_tokens": max_tokens}
  if response_format is not None:
      kwargs["response_format"] = response_format
  resp = await oa.chat.completions.create(**kwargs)
  return resp.choices[0].message.content or ""
  ```
- Pass schema at each call site:
  - `resolve_subtopics` → `schema=ChapterResolveMatches`
  - `map_sections` → `schema=ChapterMapBlock`
  - `stitch` → `schema=ChapterStitchOut`
  - `ground` → `schema=ChapterGroundOut`

### 5. `src/services/chat/agents/_scope.py`

- `_chat` grows `schema=None` and uses `apply_structured_output` (same body).
- `resolve_book` passes `schema=ChapterParse`.
- Note: shared by `qa` too — schema models unaffected, object models gain the
  `<response_format>` token. Acceptable / desirable.

### 6. `src/services/chat/agents/facilitate.py` (retrofit)

`_chat` switches its inline hint loop to `apply_structured_output` — behaviorally
identical except the hint is now `<response_format>`-wrapped. MAP/VERIFY schemas
unchanged.

## Data flow (per stage)

```
stage fn → _chat(..., schema=ChapterX)
  → apply_structured_output(messages, model, ChapterX)
      → resolve_response_format → json_mode_for(model)
        SCHEMA: (json_schema payload, None)   → messages unchanged
        OBJECT: ({"type":"json_object"}, "<response_format>…</response_format>")
                → hint appended to system message
  → create(..., response_format=payload?)
  → strip_fences + json.loads   (unchanged safety net)
```

## Error handling

- Every stage keeps its existing `try/except` fail-open (excerpt body, empty
  intro/outro, low-confidence ground, fallback BookResolution).
- Unknown model → OBJECT (never sends an unsupported schema).
- Non-introspectable schema → `(None, None)` → no payload, no token (current
  free-text behavior).

## Testing

`test_structured_output_gate.py` (extend):
- `_schema_hint`/`schema_hint` output contains `<response_format>` and `</response_format>` and "json" and the keys.
- `apply_structured_output`: OBJECT model → returns `{"type":"json_object"}` and a messages list whose system message gained the `<response_format>` token; SCHEMA model → json_schema payload and messages unchanged; no system message → token prepended as a new system message; schema=None → (messages unchanged, None).

`test_chapter_gate.py` (new):
- With an OBJECT model, `chapter._chat` (patched client) sends `json_object` and the system message carries `<response_format>`.
- With a SCHEMA model, payload is `json_schema` and system message untouched.
- `map_sections`/`stitch`/`ground`/`resolve_subtopics` pass the right schema (assert via a spy on `_chat` capturing the `schema` kwarg) — one focused test each or one parametrized test.

`test_scope_gate.py` (new):
- `resolve_book` routes `ChapterParse` through the gate: OBJECT model → token injected; SCHEMA model → native payload. Fail-open path still returns the fallback `BookResolution` on a raising client.

`test_chapter_prompts_xml.py` (new) or extend `test_t18_xml_scaffolds.py`:
- Each of the 5 `CHAPTER_*` prompts contains `<role>`, `<task>`, `<output_format>`; no legacy `ROLE:`/`OUTPUT FORMAT:` labels (there were none, but lock it).

Regression: full chat suite green. Existing facilitate/tutor tests still pass
(hint now `<response_format>`-wrapped but assertions check substrings).

## Out of scope (YAGNI)

- No change to `resume`'s pipeline diagram / modal (no new stage or node — the
  gate is an internal call-mechanism, same as the facilitate/tutor gate).
- No change to `BaseLLM` per-client `_build_response_format` (streaming path).
- `qa` mode's own non-parse prompts are untouched; only the shared parse stage
  is upgraded transitively.
```
