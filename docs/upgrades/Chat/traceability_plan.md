# Traceability & Response-Quality Upgrade Plan

> **Goal**: Perplexity-style answers — every claim carries an inline numbered
> citation `[¹]` that resolves to `(Author, Year, p. X-Y)` plus a clickable
> source card. Answers carry section structure (headers, summary, body,
> further reading). Chat UI exposes temperature + retrieval knobs.

---

## Diagnostic — example: "What is the data-generating process?"

Today's tutor response (paraphrased):
> The data-generating process is the underlying stochastic mechanism that
> produces the observations **ISLP (ch02, §2.1)**. ...

Problems:
1. **Citation format is opaque.** `ISLP (ch02, §2.1)` does not tell the reader
   who wrote it, when, or which pages — three of the four pieces of an APA
   citation are missing.
2. **Sentence-to-source mapping is invisible.** The whole paragraph cites one
   source, but the reader cannot see which specific sentence came from that
   chunk vs. the LLM's connective tissue.
3. **No structural cues.** Wall of prose; no `## Definition`, `## Example`,
   `## Further reading`.
4. **No knobs.** User cannot lower temperature for deterministic answers
   nor raise `top_k` for broader retrieval.

---

## Bottlenecks (mapped from code audit, 2026-05-18)

| ID | Bottleneck | Location |
|----|-----------|----------|
| B-T1 | `Source` Pydantic model lacks `authors`, `year`, `page_from`, `page_to`, `book_name` | `src/services/chat/schemas/_core.py:46-58` |
| B-T2 | `_point_to_source` reads only `book_slug`, `chapter_id`, `section_path`, `page` from Qdrant payload — ignores `book_name`, `authors`, `year`, `page_from`, `page_to` that the ingestion side wrote (`build_documents._flat_meta`) | `src/services/chat/retrieval.py:46-106` |
| B-T3 | `retrieve` tool payload drops author/year/page even if `Source` had them; excerpt is 200 chars | `src/services/chat/tools/retrieve.py:55-66` |
| B-T4 | Prompt: `**Book (chapter, section)**` — no author/year/page directive; no structural-header directive | `src/services/chat/prompts/tutor.py:18` |
| B-T5 | Tutor has no `response_format` → LLM emits free text, no machine-readable per-claim citation spans | `src/services/chat/mode_impls/tutor.py` |
| B-T6 | `ChatRequest` has no `temperature`, `top_k_retrieve`, `rerank` user-settable fields | `src/services/chat/schemas/_core.py` (ChatRequest) |
| B-T7 | Frontend lacks settings panel (out of backend scope; tracked here for completeness) | `web/` |

---

## Perplexity-style target

```
┌─ User: What is the data-generating process? ────────────────────────┐
│                                                                     │
│ ## Definition                                                       │
│                                                                     │
│ The data-generating process (DGP) is the unknown stochastic         │
│ mechanism by which observed data are produced[¹]. Statistical       │
│ models approximate it; the DGP itself is rarely directly            │
│ observable[²].                                                      │
│                                                                     │
│ ## Formalisation                                                    │
│                                                                     │
│ Formally, a DGP is a probability measure $P$ on a sample space      │
│ $(\Omega, \mathcal{F})$ such that observed sample $Y_i \sim P$[¹].  │
│                                                                     │
│ ## Why it matters                                                   │
│                                                                     │
│ Identifying assumptions in causal inference are statements about    │
│ properties of the DGP, not the model[²]. ...                        │
│                                                                     │
│ ──────────────────────────────────────────────────────────────────  │
│ Sources                                                             │
│  [¹] James, Witten, Hastie & Tibshirani (2023, p. 15-18). ISLP ch02 │
│      §2.1. "Statistical Learning". score 0.83. [show passage]       │
│  [²] Hayashi (2000, p. 7-11). Econometrics ch01 §1.1. "Probability  │
│      Space and Random Variables". score 0.79. [show passage]        │
└─────────────────────────────────────────────────────────────────────┘
```

Three properties:
1. **Inline numbered cite** `[¹]` rendered as a small badge.
2. **Sources panel** at the bottom shows full APA-ish form + the actual
   retrieved chunk on demand.
3. **Sentence ↔ chunk binding** kept structurally — not just in prose.

---

## Tickets (P0)

Each ticket: goal, files, approach, tests, acceptance, rollback.

### T13-A — Extend `Source` schema with full provenance · S

**Goal**: `Source` carries everything the LLM needs to cite APA-style.

**Files**:
- `src/services/chat/schemas/_core.py` — add `authors: str`, `authors_short: str`,
  `year: int | None`, `book_name: str`, `page_from: int | None`,
  `page_to: int | None` (with defaults so legacy callers do not break).

**Tests**:
- `test_t13a_source_schema.py` — round-trip via `model_validate_json`;
  defaults populate when fields absent.

**Acceptance**: existing 300-test suite still passes; new fields readable.

**Rollback**: revert single commit.

---

### T13-B — `_point_to_source` reads full Qdrant payload · S

**Goal**: surface all metadata the ingestion side wrote.

**Files**:
- `src/services/chat/retrieval.py:_point_to_source` — read `payload["book_name"]`,
  `payload["authors"]`, `payload["year"]`, `payload["page_from"]`,
  `payload["page_to"]` with graceful fallbacks.
- Helper `_authors_short(authors: str) -> str` for "Smith et al." form.

**Tests**:
- `test_t13b_point_to_source.py` — synthetic Qdrant point with all metadata
  → `Source` carries it; missing metadata → defaults; CSV-string authors
  split correctly.

**Rollback**: revert single commit.

---

### T13-C — Enrich `retrieve` tool payload · S

**Goal**: tool result the LLM sees includes author/year/pages + meaningfully
sized chunk text.

**Files**:
- `src/services/chat/tools/retrieve.py` — extend payload dict with
  `authors`, `authors_short`, `year`, `book_name`, `page_from`, `page_to`,
  `chunk` (truncated to ~1500 chars — large enough to ground, small enough
  not to balloon context).
- Backwards-compat: keep `excerpt` (200 chars) for any caller that already
  uses it; add `chunk` as the primary text.

**Tests**:
- `test_t13c_retrieve_payload.py` — JSON list returned by tool contains all
  fields. Snapshot the structure.

---

### T13-D — APA-style citation directive in prompt + structure · M

**Goal**: prompt the LLM to emit `[¹]` inline and a sources block per ICMJE-ish
template, with sections.

**Files**:
- `src/services/chat/prompts/tutor.py` — replace `TUTOR_INSTRUCTIONS` with a
  longer version that:
  - Asks for sections (`## Definition`, `## Formalisation`, `## Why it matters`,
    `## Further reading`) tailored to the question type.
  - Asks for inline numbered cites `[¹]` `[²]` …
  - Asks for a final `## Sources` block with full APA-ish entries:
    `[¹] {authors_short} ({year}). *{book_name}*, {chapter} §{section}, pp. {page_from}-{page_to}.`
  - Mandates one cite per non-trivial sentence.

**Tests**:
- `test_t13d_prompt.py` — string-level assertions on the new prompt
  constants. End-to-end mock-LLM test to confirm the prompt is passed
  through to `create_agent`.

---

### T13-E — Structured citation schema (`TutorAnswer` v2) · M

**Goal**: optional `response_format` for tutor that exposes per-claim citation
spans so the frontend can render `[¹]` as a real React component.

**Files**:
- `src/services/chat/schemas/output.py` — extend `TutorAnswer`:
  ```python
  class TutorCitation(BaseModel):
      index: int                       # 1-based [¹] number
      chunkId: str
      authors_short: str
      year: int | None
      book_name: str
      chapter: str
      section: str
      page_from: int | None = None
      page_to: int | None = None
      quote: str = ""                  # the exact sentence the cite supports

  class TutorAnswer(BaseModel):
      text: str                        # markdown with [¹] markers
      sections: list[str] = []         # H2 headings used
      citations: list[TutorCitation]
      math_blocks: list[str] = []
      figures: list[FigureRef] = []
  ```
- `src/services/chat/mode_impls/tutor.py` — add `response_format=TutorAnswer`
  to the `create_agent` call (was previously free-form). Keep an env
  override `TUTOR_FREE_TEXT=1` to roll back if schema-constrained answers
  underperform.

**Tests**:
- `test_t13e_tutor_schema.py` — `TutorAnswer.model_json_schema()` is
  OpenAI-compatible; sample payload validates.

---

### T13-F — User-controllable temperature + retrieval knobs · S

**Goal**: `ChatRequest` accepts `temperature`, `top_k`, `rerank` from the
frontend.

**Files**:
- `src/services/chat/schemas/_core.py` (ChatRequest):
  ```python
  temperature: float | None = None      # None → mode default
  top_k: int | None = None               # None → 5
  rerank: bool | None = None             # None → mode default
  ```
- `src/services/chat/mode_impls/tutor.py` + `_common.py` — thread to
  `create_agent` when the kwarg is supplied. Plumb via the agent's invoke
  config (LangChain forwards model kwargs).
- `src/services/chat/router.py` — pass `temperature` into `agent.astream`'s
  config; bound retrieval params propagate via tool calls (the LLM still
  decides when to call `retrieve`, but the bound defaults shift).

**Tests**:
- `test_t13f_chat_request_knobs.py` — `ChatRequest` accepts new fields;
  rejects out-of-range temperature (>2 or <0).

---

### T13-G — Frontend settings tab (documentation only) · S

**Goal**: out of backend scope. Record the API contract so a frontend ticket
can implement the panel.

**Files**:
- `docs/services/modes/README.md` — add "Chat UI settings" section listing
  the new `ChatRequest` fields.
- `docs/upgrades/Chat/traceability_plan.md` (this file) — frontend ticket
  shape for the team.

---

## Test plan summary

| Ticket | Unit tests | Integration | Perf bench |
|--------|-----------|------------|-----------|
| T13-A  | schema round-trip | — | — |
| T13-B  | payload → Source w/ all fields | — | — |
| T13-C  | tool payload shape | — | — |
| T13-D  | prompt constants | mock-LLM end-to-end | — |
| T13-E  | schema OpenAI-compat | tutor run yields valid TutorAnswer | latency unchanged (<5% delta) |
| T13-F  | request validation | knobs reach create_agent | — |
| T13-G  | doc-only | — | — |

All tickets must keep the 300-test suite green.

---

## Acceptance criteria (whole batch)

- A tutor response cites at least one source by author + year + page range.
- Tutor response includes ≥ 2 H2 section headers when the question warrants
  (definition + example + further reading).
- `ChatRequest` accepts `temperature`, `top_k`, `rerank`.
- Existing v1 path still works under `USE_V2_MODES=""`.
- Test suite green (≥ 300 + new T13 tests).

---

## Out of scope (Phase 2+ candidates)

- NLI citation verification post-stream (would catch unsupported sentences).
- Sentence-level highlight binding (would feed `quote` field via NLI rather
  than asking the LLM to populate it).
- Streaming partial JSON for `TutorAnswer` so the UI renders sections + cites
  as they arrive instead of after the stream completes.
- Frontend settings panel implementation (separate ticket).
