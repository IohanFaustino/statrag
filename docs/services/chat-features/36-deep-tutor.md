# 36 — Deep tutor pipeline (v2 multi-aspect)

> **See also**: [39-image-judge.md](39-image-judge.md) for the image
> branch (concept-density image retrieval + two-tier pertinence judge)
> that runs in parallel with the text density branch and contributes
> up to 3 vision-approved figures to each answer.

## Purpose

Long-form, structured textbook-grade answer with explicit per-aspect
content and tight latency budget.

Two big design moves over v1:

1. **Multi-aspect schema** — the LLM is forced to fill seven explicit
   fields (``tldr``, ``definition``, ``formal_statement``,
   ``intuition``, ``examples``, ``trade_offs``, ``further_reading``)
   rather than emitting a single ``text`` blob. Each field has a per-
   field word-count target in the system prompt, so the model can no
   longer skimp on length.
2. **Latency cuts** — reranker pre-warmed at import, concept
   extraction parallelised with the wide RRF candidate pull, critique
   loop OFF by default, density-stage caps tightened.

## Pipeline

```mermaid
graph TD
  Q[user query] --> P[parallel]
  P -->|asyncio.gather| EX["query planner / extract_concepts_ex (nano)<br/>concepts + budget + queries[] + facets[]"]
  P -->|asyncio.gather| RR["raw-query wide pull (Qdrant, no rerank)"]
  EX -->|queries ‖| MQ["multi-query pulls → RRF merge<br/>(TUTOR_MULTI_QUERY)"]
  RR --> MQ
  MQ --> DS["density_select (alpha=TUTOR_DENSITY_ALPHA)<br/>count concepts → top sections → scroll<br/>+ adjacent sibling-section expansion (TUTOR_NEIGHBOR_EXPAND)<br/>→ rerank (the gate)"]
  DS --> DV["author-diversity select<br/>round-robin authors + year tiebreak<br/>(TUTOR_DIVERSITY / diversityAuthors)"]
  DV --> CC["coverage check (nano): facets vs sources<br/>re-query missing (cap 1) → re-rank<br/>(TUTOR_COVERAGE_CHECK)"]
  CC --> M{sources empty?}
  M -->|yes| FAIL["## No corpus coverage"]
  M -->|no| PLAN["synthesis plan (parallel w/ figure judge)<br/>thesis + per-aspect outline + evidence ledger<br/>+ author contrasts (TUTOR_SYNTHESIS_PLAN / stageModels.plan)<br/>'off' = skip → legacy single-draft"]
  PLAN --> WF{tutorWorkflow?}
  WF -->|single default| DR["draft (single call, streamed)<br/>response_format = DeepTutorAnswer<br/>follows the plan: thesis + ledger + contrasts"]
  WF -->|orchestrator| WK["per-author workers ‖ (one AuthorBrief each)"]
  WK --> SY["synthesizer (streamed, DeepTutorAnswer)<br/>integrate briefs + compare authors"]
  SY --> CRT
  WK -.->|<2 authors or all fail| DR
  DR --> CRT{TUTOR_DEEP_CRITIQUE?}
  CRT -->|0 default| FIN
  CRT -->|1 opt-in| CR[critique]
  CR --> Q1{complete?}
  Q1 -->|yes| FIN
  Q1 -->|no, iter<cap| RF[refine retrieve + redraft]
  RF --> CR
  Q1 -->|cap| FIN[convert -> TutorAnswer<br/>(text + aspects + citations)]
  FIN --> SSE["meta → token* (per-aspect attribution)<br/>→ structured_output → sources_full<br/>→ retrieval_meta (incl. timings) → usage → done"]
```

## Schema (LLM contract)

```python
class DeepTutorAnswer(BaseModel):
    tldr: str               # 40-80 words direct answer
    definition: str         # 120-180 words
    formal_statement: str   # 120-200 words math / formal
    intuition: str          # 140-220 words plain-language
    examples: str           # 150-250 words worked example(s)
    trade_offs: str         # 130-200 words caveats, alternatives
    further_reading: str    # 50-100 words pointers
    citations: list[TutorCitation]
    math_blocks: list[str] = []
    figures: list[FigureRef] = []
```

Target total: ~1000-1500 words.

The pipeline converts it to a backward-compat ``TutorAnswer``:
- ``text`` — assembled markdown with ``## H2`` per aspect (canonical order).
- ``aspects`` — raw aspect strings (NEW field, default ``{}``) for aspect-aware UIs.
- ``citations`` — reconciled against the source bundle (chunkId → enriched metadata).

### Conversion-time enhancements (added 2026-05-19)

In ``_convert_to_tutor_answer``:

1. **LaTeX escape repair** — every aspect string passes through
   ``_repair_latex_post`` (re-attaches `\` to TAB/NL/BS/FF/CR control
   chars that JSON already collapsed onto known latex stems, e.g.
   TAB+`heta` → `\theta`). Raw JSON sources also pre-pass through
   ``_repair_latex_escapes`` before ``json.loads`` to double single
   backslashes preceding ~80 whitelisted command names.
2. **Bare-math wrap** — ``_wrap_bare_math`` bundles contiguous math
   token runs (`\command` + `^_`{...}` + isolated single letters + math
   operators) in `$..$` so KaTeX activates even when the LLM forgot
   delimiters.
3. **Figure injection** — for each approved figure (from the image
   judge, feature 39), inject a three-part block into the target
   aspect: `lead` → `![cap](url)` → `explanation`. Aspect selected by
   ``_choose_target_aspect`` which scores each aspect body's token
   overlap with caption + judge_reason. TL;DR is excluded from
   auto-placement (kept concise). Lead sentence built by
   ``_build_lead`` from role-aware varied template banks
   (``_LEAD_TEMPLATES`` per role, ``_LEAD_GENERIC``, ``_LEAD_NO_TOPIC``);
   role `"other"` normalised to `"figure"`.

## Files

| Path | Role |
|---|---|
| `src/services/chat/schemas/output.py` | `DeepTutorAnswer`, `TutorAnswer.aspects` |
| `src/services/chat/prompts/deep_tutor.py` | system prompts + `assemble_markdown` |
| `src/services/chat/retrievers/density.py` | concept-density helpers |
| `src/services/chat/agents/deep_tutor.py` | pipeline entry + draft streaming |
| `src/services/chat/router.py` | dispatch (env-gated) |
| `src/services/chat/tests/test_deep_tutor.py` | 45 tests (was 21; +24 covering latex repair, figure injection, aspect scoring, lead templates, math wrapping) |

## SSE protocol additions

The ``token`` event now carries optional attribution:

```json
{"type": "token", "text": "…delta…", "aspect": "definition", "heading": "Definition"}
```

Frontends that don't know about ``aspect``/``heading`` can ignore them
— the ``text`` field is identical to v1.

The ``retrieval_meta`` event includes ``timings`` (ms per phase):

```json
{"type": "retrieval_meta", "meta": {..., "timings": {
  "parallel_extract_retrieve_ms": 480,
  "density_ms": 220,
  "draft_ms": 6500
}}}
```

## Env tunables

| Var | Default | Meaning |
|---|---|---|
| `TUTOR_DEEP_MODE` | `1` | `0` = revert to legacy `create_agent` path |
| `TUTOR_DEEP_CRITIQUE` | `0` | `1` = enable critique + refine loop |
| `TUTOR_DEEP_MAX_REFINE` | `1` | Hard cap on refine iterations |
| `TUTOR_DEEP_TOP_SECTIONS` | `4` | Sections expanded after density rank |
| `TUTOR_DEEP_FINAL_TOP_N` | `8` | Sources surviving rerank |
| `TUTOR_DEEP_MAX_CHUNKS_PER_SECTION` | `6` | Scroll cap per section |
| `TUTOR_DEEP_MAX_TOKENS` | `8000` | `max_completion_tokens` for draft / synthesizer — generous ceiling so the draft can be extensive without truncating (4000→6000→8000) |
| `TUTOR_DEEP_TEMPERATURE` | `0.4` | Draft creativity. Applies to ALL draft paths (OpenAI structured stream, deepseek router, json fallback). Was uncontrolled (~1.0 model default) on the structured path. Plan/extract/judge/coverage stay `0.0`. The structured-stream call passes it; the `parse()` fallback omits it so a reasoning-model temp-reject degrades cleanly. |
| `TUTOR_DEEP_WARM` | `1` | `0` = skip reranker pre-warm thread |
| `TUTOR_NEIGHBOR_EXPAND` | `1` | `0` = same-section expansion only (skip adjacent sibling-section expansion) |
| `TUTOR_DENSITY_ALPHA` | `0.6` | Concept-TF weight in section scoring (higher = term frequency matters more vs RRF) |
| `TUTOR_MULTI_QUERY` | `1` | `0` = retrieve on the raw question only (skip the query planner's multi-query + RRF) |
| `TUTOR_DEEP_VISION_EXPLAIN` | `lazy` | Tri-state: `"lazy"` (default) = no inline vision call, figures render with caption+judge_reason; `"1"` = explain only the single top-ranked figure (1 vision call max); `"0"` = off. Changed from `"1"` default in Phase-1 (2026-05-30) to save 2–3 vision calls per turn. |
| `TUTOR_DEEP_VISION_MODEL` | `gpt-4o-mini` | Vision model used when `TUTOR_DEEP_VISION_EXPLAIN=1` |
| `TUTOR_COVERAGE_CHECK` | `1` | `0` = skip the facet coverage check + re-query entirely. When `1`, an additional gate applies: coverage runs only when `len(facets) >= 4` or any facet contains `$` or the word `formula` — simple questions skip the extra nano call (see Phase-1 coverage gate). |
| `TUTOR_SYNTHESIS_PLAN` | `1` | `0` = skip the synthesis-plan step (legacy single-draft). Per-request: `stageModels.plan = "off"` or a model id |
| `TUTOR_WORKFLOW` | `single` | Drafting workflow default; `orchestrator` = per-author workers + synthesizer; `organize` = long-context organizer (§11/48). Per-request: `tutorWorkflow` |
| `TUTOR_WORKER_MODEL` | nano | Model for orchestrator worker calls (synthesizer uses the Draft-node model) |
| `TUTOR_ORGANIZE_MODEL` | `deepseek-v4-pro` | Model for the `organize` workflow — reads a large pool, organizes pieces into fields (§48) |
| `TUTOR_ORGANIZE_MAX_TOKENS` | `120000` | Token budget (≈ chars/4) for the organizer's source pool; safe-truncates, never assumes a 1M window |
| `TUTOR_ORGANIZE_POOL` | `60` | Max chunks reranked into the organizer pool before token-budget trim |
| `TUTOR_DIVERSITY` | `1` | `0` = disable author-perspective diversity selection |
| `TUTOR_DIVERSITY_MAX_AUTHORS` | `6` | Hard cap / `auto` ceiling on distinct authors. Honored end-to-end: section budget scales to `max(TUTOR_DEEP_TOP_SECTIONS, target)` and the final rerank keeps ≥1 chunk per picked author (author-aware floor), so a chosen N is not silently clamped to ~3 by the relevance trim. Still bounded by distinct authors present in the candidate pool. |
| `TUTOR_DIVERSITY_DEFAULT` | `auto` | Mode when request omits `diversityAuthors` (`auto`/`off`/int) |
| `TUTOR_DIVERSITY_TARGET_AUTHORS` | `3` | Legacy fallback for the cap |

`diversityAuthors` (request): `"auto"` = concept-extraction model picks the count (clamped to the cap **and** to authors available in the pool); `0`/`1` = off; `N≥2` = hard cap. Effective count is always ≤ authors available, so a single-author topic yields one author.

## Tests

21 cases:

- density helpers (count, score blending, hyphen tokens)
- concept extraction (parse, cap, heuristic fallback)
- critique (parse, empty-draft, error degradation)
- conversion (aspects fill, error recovery, sections list)
- citation reconciliation
- merge sources (dedup + renumber)
- full SSE sequence (meta → token → structured_output → sources_full → retrieval_meta → usage → done)
- token events carry aspect attribution
- critique off by default (count = 0)
- critique on via env triggers exactly 1 critique call
- empty corpus short-circuit
- mocked end-to-end latency < 2s
- aspect minimum word count
- total word count ≥ 400 (with canned answer)
- no copy-paste verbatim span ≥ 80 chars
- aspects field survives `model_dump()`

## Refinement guide (live tuning)

When measuring real latency, the ``retrieval_meta.timings`` block tells
you which phase dominates. Tune accordingly:

| Phase slow | Knob |
|---|---|
| `parallel_extract_retrieve_ms` > 1500 | reduce `rerank_top_k_in` (in settings) |
| `density_ms` > 1000 | drop `TUTOR_DEEP_TOP_SECTIONS` to 3, `TUTOR_DEEP_MAX_CHUNKS_PER_SECTION` to 4 |
| `draft_ms` > 12000 | reduce `TUTOR_DEEP_MAX_TOKENS` to 3000 or trim source bundle |

## Rollback

`TUTOR_DEEP_MODE=0` in `.env` → router falls back to legacy `_tutor_v2`.

## 2026-05-20 — format pass (9 items)

Answer-shape refinements (changelog #57). Highlights for operators:

- **Introduction** replaces "TL;DR" (heading only; key `tldr` unchanged) and
  now ends with a one-sentence roadmap of the sections that follow.
- **Per-claim attribution**: multi-source paragraphs no longer pool two
  books behind one `[N]`; the definition prefers one bullet per source.
- **Verbatim formal statement**: when a source states the theorem, it is
  reproduced word-for-word as a Markdown `>` blockquote with `[N]`
  (renders via the new `quote` block in `TutorView`); otherwise an
  indirect cite. The end-reference hyperlink is the existing citation card.
- **Example relevance audit**: every answer carries
  `TutorAnswer.quality["example_relevance"]` ∈ [0,1] (lexical overlap of
  the example with definition+formal+intuition); < 0.15 logs a warning.
  The example body also ends with a "**Why this example fits:**" note.
- **Vision-explain (figures)**: `TUTOR_DEEP_VISION_EXPLAIN` is a tri-state.
  `"lazy"` (default since Phase-1 2026-05-30) emits no inline vision call;
  figures render with caption + judge_reason text. `"1"` makes a vision model
  (`TUTOR_DEEP_VISION_MODEL`, default `gpt-4o-mini`) read only the **single
  top-ranked figure** (capped from the original up-to-3). `"0"` = off.
  The placement code already falls back gracefully when no explanation is
  present, so lazy mode has zero quality cost.

Contracts locked by `src/services/chat/tests/test_tutor_prompt_contract.py`
and `web/src/components/views/TutorView.{emphasis,blocks}.test.tsx`.


---

**2026-05-20 update — vision explain default flipped**

`build_vision_explanations()` now runs by default; `_VISION_EXPLAIN_PROMPT` rewritten for grounded figure descriptions. Backend restart needed to pick up the env default. See changelog 2026-05-20 §2.
