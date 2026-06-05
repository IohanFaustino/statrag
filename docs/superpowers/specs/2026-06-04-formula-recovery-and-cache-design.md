# Formula recovery (vision second-RAG) + global formula cache

**Date:** 2026-06-04
**Status:** design (awaiting review) — **plan-only this cycle; execution deferred to a fresh session.**
**Scope:** deep-tutor synthesis (`agents/orchestrator_workers.py` + 3 new modules + 1 prompt line). No frontend/response-schema-field change.

## Problem

The `definition` aspect still under-states defining equations (e.g. Bias/Variance) because the crucial equations are frequently OCR'd into **dropped image placeholders** (`![art](…/Art_P760.jpg)`) — the formula *text is gone from the chunk*, only surrounding prose survives. The previous cycle made workers preserve equations and the synth reconstruct them, but reconstruction is from memory (inconsistent, not the source's verbatim formula). The retrieved corpus simply lacks the equation as text, so no amount of prompt tuning recovers it.

Two independent gaps:
1. **No capacity to recover an equation that exists only as an image.** The figure image *does* contain the equation; we have `search_figures()` + `inspect_figure()` (gpt-4o vision) but never use them to read an equation back as text.
2. **No memory of equations already found.** Each query re-derives formulas from scratch → run-to-run variance (observed: 18 vs 4 `$` on identical queries).

## Decisions (locked with the user)

- **Scope this cycle:** #3 formula-recovery subagent **+** #2 global formula cache. Defer #1 (merging planner+draft+synth into one deep agent) — the prior eval showed the deep agent is ~5× slower with no quality gain.
- **"Subagents" = lightweight `asyncio.gather`** parallel tasks (NOT deepagents `SubAgentMiddleware`) — keeps the lean-structured live path fast (~52–69 s).
- **Recovery source:** **vision-on-image first, text re-query fallback.** First `search_figures(concept+"formula")` → `inspect_figure` (vision transcribes the LaTeX off the dropped equation image); if that yields nothing, a formula-scoped `hybrid_search` over text collections.
- **Trigger:** **on detected gap only** — recovery runs only when a concept's defining equation is missing as clean LaTeX AND an `![…]` placeholder sits near its definitional text. No cost on queries whose formulas are already present.

## Existing infrastructure to reuse (do not rebuild)

- `src/services/chat/retrieval.py` — `search_figures(query, book_slugs, k) -> list[Figure]`; `hybrid_search(query, book_slugs, top_k, rerank) -> (sources, ctx)`.
- `src/services/chat/tools/inspect_figure.py` — `async inspect_figure(figure: Figure, *, query) -> str` (gpt-4o vision on the figure URL; returns text; empty string on failure / no URL).
- `src/services/chat/schemas/_core.py:72` — `Figure` (has `caption`, `url`/`chart`, `book`, …).
- `src/core/qdrant_store.py` — `client()`, `TEXT_VECTOR="text"`, `ensure_text_collection(name)`, `DENSE_DIM=3072`.
- `src/services/chat/memory.py` — reference pattern for embed→upsert→semantic-search a Qdrant collection (mirror its `openai.embeddings.create(settings.embedding_model)` + `PointStruct(vector={TEXT_VECTOR: emb})` + `client().query_points(..., using=TEXT_VECTOR)`).
- `src/services/chat/agents/orchestrator_workers.py` — `run_orchestrator_workers(query, sources, plan, …)`; the L0 synth `user` message is built right after the `if level==5` block (around the `plan_block = _format_plan_block(plan)` line). `book_slugs` derive from `{s.book for s in sources}`.

## Architecture

A **formula-recovery stage** inserted in `run_orchestrator_workers` after the worker briefs and before the L0 structured-synth `user` message, backed by a **global formula cache**.

```
workers → briefs ─┐
sources ──────────┼─► detect_formula_gaps(sources, query) → list[GapConcept]
                  │        (definitional text present, equation absent as LaTeX,
                  │         and a ![…] image placeholder nearby)
                  ▼
          recover_formulas(query, gaps, book_slugs):   # asyncio.gather over gaps
             cache_lookup(concept) ──hit──► RecoveredEquation (no LLM/vision cost)
                  │ miss
                  ▼
             search_figures(concept+" definition formula") → inspect_figure(vision)
                  │ none
                  ▼
             hybrid_search(concept+" is defined as", text) → extract $…$
                  │
                  ▼
             cache_write(concept, latex, citation)
                  ▼
          <recovered_equations> block → appended to synth user message
                  ▼
          L0 structured synth (DEEP_TUTOR_INSTRUCTIONS: use them verbatim)
```

Best-effort throughout: any failure yields no recovered equations and the synth degrades to today's behavior.

## Components

### 1. `src/services/chat/agents/formula_gaps.py`
- `GapConcept` (dataclass/pydantic): `{term: str, hint: str, book_slugs: list[str]}` — `term` = concept whose equation is missing; `hint` = the nearby definitional sentence (used to focus the figure search); `book_slugs` = books where the gap appeared.
- `detect_formula_gaps(sources: list[Source], query: str) -> list[GapConcept]` — **pure, no LLM.** For each source chunk: find definitional spans (regex for "is defined as", "defined to be", "bias/variance of … is", or a heading like "Bias of an estimator"); if such a span has NO clean LaTeX equation (`$…$`/`$$…$$`) within ~200 chars BUT has an image placeholder `![…](…)` within ~200 chars, emit a `GapConcept` (term from the heading/definiendum, hint = the span, book_slugs=[chunk.book]). Dedupe by normalized term. Cap at N gaps (e.g. 4) to bound cost.

### 2. `src/services/chat/agents/formula_recovery.py`
- `RecoveredEquation` (pydantic): `{term: str, latex: str, citation: str}` (`citation` = "Author (year), §section" of the figure/source).
- `async recover_formulas(query, gaps, *, vision_model=None) -> list[RecoveredEquation]` — `asyncio.gather` per gap:
  1. `cache_lookup(gap.term)` → on hit return its `RecoveredEquation` (skip vision).
  2. `figs = search_figures(f"{gap.term} definition formula equation", book_slugs=gap.book_slugs, k=2)`; for the top figure, `txt = await inspect_figure(fig, query=f"Transcribe the exact equation/definition for {gap.term} as LaTeX, delimited with $…$ or $$…$$. Output only the equation.")`. Extract a `$…$`/`$$…$$` from `txt`.
  3. Fallback: `sources,_ = hybrid_search(f"{gap.term} is defined as the formula", book_slugs=gap.book_slugs, top_k=3, rerank=False)`; extract the first `$…$` whose surrounding text mentions the term.
  4. On success: `cache_write(gap.term, latex, citation)`; return `RecoveredEquation`. On total miss: omit (no fabrication).
- `format_recovered_block(eqs) -> str` — renders `<recovered_equations>` for the synth prompt (term → latex + citation).

### 3. `src/services/chat/agents/formula_cache.py`
- Global Qdrant collection **`formula_cache`** (single 3072d `TEXT_VECTOR`, cosine), created lazily via `ensure_text_collection("formula_cache")`. Payload: `{term, latex, citation, created_at}`.
- `async cache_lookup(term: str, *, threshold: float = 0.93) -> RecoveredEquation | None` — embed `term`, `query_points(formula_cache, using=TEXT_VECTOR, limit=1)`; return the hit only if score ≥ threshold.
- `async cache_write(term, latex, citation) -> None` — embed `term`, upsert a `PointStruct` (uuid5 of normalized term as id, so re-writes overwrite). Best-effort; never raises into the caller.
- Mirror `memory.py`'s embed/upsert/search code exactly (same client, vector name, embedding model).

### 4. Synth wiring + prompt
- In `run_orchestrator_workers`, just before building the L0 synth `user` string: `gaps = detect_formula_gaps(sources, query)`; `recovered = await recover_formulas(query, gaps) if gaps else []`; insert `format_recovered_block(recovered)` into the `user` message (a new `<recovered_equations>` block, between the source bundle and the briefs). Guard the whole thing in try/except → `[]` on failure.
- `DEEP_TUTOR_INSTRUCTIONS`: add one rule — "If a `<recovered_equations>` block is present, use the given LaTeX VERBATIM as the named concept's defining equation in its `### ` subsection (cite the provided citation)."

## Data flow / contracts

- `detect_formula_gaps` consumes `Source` (has `.chunk`, `.book`, `.section`), returns `GapConcept`s — no I/O, deterministic.
- `recover_formulas` is the only async/LLM/IO unit (vision + retrieval + cache). Returns possibly-empty `list[RecoveredEquation]`.
- The synth receives recovered equations as prompt text; it still emits the same `DeepTutorAnswer` schema (no schema change).

## Error handling

- Every external call (`search_figures`, `inspect_figure`, `hybrid_search`, Qdrant cache) wrapped best-effort; failures drop that gap, never crash the answer.
- `cache_write` failures are swallowed (cache is an optimization).
- Gap cap (≤4) bounds vision cost; cache hits avoid vision entirely on repeat concepts.

## Testing

- `formula_gaps`: unit tests on fixture chunks — (a) chunk with `![art](…)` near "Bias of an estimator" + no `$…$` → emits a gap; (b) chunk with a clean `$E(\hat\mu)=\mu$` near the definiendum → NO gap; (c) dedupe; (d) cap.
- `formula_recovery`: monkeypatch `search_figures`/`inspect_figure`/`hybrid_search`/cache — assert vision-first, text-fallback, cache-hit short-circuit, and `$…$` extraction; assert `asyncio.gather` parallelism (all gaps attempted).
- `formula_cache`: monkeypatch Qdrant client + embeddings — assert lookup threshold gating, write/overwrite by stable id, best-effort swallow on error. (No live Qdrant in unit tests.)
- Prompt contract: `DEEP_TUTOR_INSTRUCTIONS` contains the `<recovered_equations>` verbatim rule.
- Integration (mocked): `run_orchestrator_workers` with a gap-containing source injects a `<recovered_equations>` block into the synth `user` message (capture via the `_stream_structured` monkeypatch already used in other tests).
- Manual (execution session, not now): live bias-variance via `orchestrator-deep` — confirm a recovered verbatim equation appears + a second identical query is served from cache (consistent output, no vision call).

## Non-goals

- No deepagents subagents / `SubAgentMiddleware` (lightweight async only).
- No #1 (merge planner+draft+synth into one deep agent) — deferred.
- No mutation of the ingested textbook collections / no re-ingestion (cache is a separate chat-service collection; respects the Chinese wall + ingestion gates).
- No frontend change, no new response-schema field.

## Open execution notes (for the fresh session)

- Confirm `Figure` field names (`url` vs `chart`) when calling `inspect_figure` — read `schemas/_core.py:72` first.
- Confirm `search_figures` returns `Figure` with a usable image URL for vision (it may be a built-in chart kind with no URL → `inspect_figure` returns "" → fallback fires).
- `formula_cache` collection is global/persistent; add it to any collection-registry doc if such a list is maintained.
