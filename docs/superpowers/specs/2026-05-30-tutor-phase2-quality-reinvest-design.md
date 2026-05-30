# Deep-Tutor Efficiency — Phase 2: Quality Reinvestment

**Date:** 2026-05-30
**Status:** Approved (design) — model choice locked by measured A/B
**Depends on:** Phase 1 (committed `b765aa8`)

## Background

Phase 1 cut waste (vision lazy, prompt diet, coverage gate) with no quality
regression. Phase 2 reinvests the freed budget into quality, targeting the
user's reported pains:

1. Lost articulation between sections (need connectors / throughline).
2. Short/incomplete examples, intuition, applications.
3. Definition decomposition (compound concepts not broken into parts).
4. Association tunnel-vision (anchors one parent, e.g. MSE only, misses other
   framings).

## Measured baseline (current nano draft, 4 queries)

| Query | total | est tok | coverage | plan | draft |
|---|---|---|---|---|---|
| Define variance | 38.3s | 2306 | 4.7s | 7.6s | 18.4s |
| Bias-variance | 156.2s | 2944 | 9.5s | 13.3s | **134.3s** |
| Overfitting | 33.6s | 2959 | 1.2s | 4.9s | 20.9s |
| L1 vs L2 | 46.2s | 2500 | 2.9s | 16.1s | 20.4s |

Draft dominates latency and is wildly variable on nano (18–134s).

## Draft-model A/B (measured, same 2 queries)

| Draft model | Define variance | Bias-variance | LaTeX | Verdict |
|---|---|---|---|---|
| `gpt-5.4-nano` (current) | 18s | **134s** (spike) | clean | inconsistent |
| `deepseek-v4-pro` | 160s | empty/timeout | **broken** | REJECTED |
| **`gpt-5.4-2026-03-05` (full)** | 42s | 40s | clean | **WINNER** |

Full model: steadier latency (no spikes; 3× faster than nano on the hard
query), clean LaTeX, and visibly stronger articulation + decomposition framing
("We build the idea in three pieces—bias, variance, and the MSE that combines
them"). Token bump ~2670 → ~2800 is modest and covered by Phase 1's freed input
budget. **deepseek-v4-pro rejected** (9× slower, timeouts, broken math escaping
on the JSON path — consistent with the known v4 thinking-mode empty-content
issue).

## Goal

Reinvest into quality: upgrade the draft model to the full OpenAI model, widen
concept association via a planner facet, and diversify retrieval by topic — net
tokens roughly flat (Phase 1 savings offset the larger draft), quality up.

## Scope — three changes

### 1 · Draft model → `gpt-5.4-2026-03-05` (full)

- **Artifact:** `src/core/config.py` (or wherever the draft-stage default model
  resolves in `deep_tutor.py` `_resolve_stage_model("draft", …)`); env table in
  doc 36.
- **Change:** the **draft** stage default becomes `openai_model_full`
  (`gpt-5.4-2026-03-05`) instead of nano. ALL OTHER stages (extract/planner,
  coverage, plan, image_judge, synthesizer worker) stay on nano — only the
  final draft is upgraded. Add env `TUTOR_DRAFT_MODEL` (default
  `openai_model_full`) so it is tunable/revertible without code.
- **Data flow:** draft node resolves its model from the new env/default;
  structured-stream path unchanged (full model is OpenAI, supports the same
  `beta.chat.completions.stream` + `response_format`).
- **Error handling:** unchanged — the existing `parse()` / json fallback still
  applies. Reverting to nano is `TUTOR_DRAFT_MODEL=gpt-5.4-nano-2026-03-17`.
- **Latency note:** draft ~40s steady. Acceptable; `TUTOR_DEEP_MAX_TOKENS`
  already caps runaway length.

### 2 · Planner related-framings facet (association breadth)

- **Artifact:** `src/services/chat/prompts/deep_tutor.py`
  `EXTRACT_CONCEPTS_BUDGET_PROMPT`; tests in `tests/test_deep_tutor.py`.
- **Change:** extend the planner's `facets` contract to ALWAYS include one
  **related-framings facet** — the OTHER contexts/parents the concept belongs
  to, not just the most obvious one. Example for bias-variance: in addition to
  the MSE decomposition facet, add "other contexts where the bias-variance
  tradeoff arises (e.g. regularization, model selection, ensemble methods)".
  Add a matching retrieval query so those framings are actually retrieved.
- **Data flow:** no new LLM call — the planner already runs once; this enriches
  its output schema/instructions. The extra `queries` entry flows into the
  existing multi-query RRF pull.
- **Error handling:** planner already degrades to a keyword heuristic on parse
  failure (`extract_concepts_ex` except branch) — unchanged.
- **Token effect:** ~neutral (one extra short retrieval query; no extra LLM
  round-trip).

### 3 · Topic-diversity in selection

- **Artifact:** `src/services/chat/agents/deep_tutor.py` density/selection path
  (the author-diversity round-robin); doc 36 + doc 42 (author-diversity).
- **Change:** the current diversity selection round-robins by **author**. Add a
  light **topic/section diversity** tiebreak so the surviving sources are not
  all from the same parent section/chapter (which is what causes MSE
  tunnel-vision). Keep author-diversity primary; add section-parent spread as a
  secondary key so at least one source from a *different* framing survives the
  final trim when present in the pool.
- **Data flow:** post-rerank selection only; no new I/O or LLM call.
- **Error handling:** pure-local; degrades to current author-only behavior if
  section metadata is missing.
- **Token effect:** none (selection re-ordering).

## Verification

1. `pytest src/services/chat/tests/test_deep_tutor.py` green (+ new facet tests).
2. Re-run the 4 baseline queries (Define variance, Bias-variance, Overfitting,
   L1 vs L2) on :5175 / via SSE. Capture timings + tokens. Compare to baseline:
   - draft latency should be steady ~40s (no 134s spikes).
   - net tokens vs Phase-0 baseline roughly flat or modestly up.
   - association: bias-variance answer should now reference framings beyond MSE
     (regularization / model selection) when the corpus supports them.
3. Browser check on :5175: articulation reads as one throughline; definition
   decomposes; no LaTeX regression.

## Interconnected artifacts (lockstep)

| Aspect | File |
|---|---|
| Backend logic | `agents/deep_tutor.py` (draft-model resolve, topic diversity) |
| Prompts | `prompts/deep_tutor.py` (`EXTRACT_CONCEPTS_BUDGET_PROMPT`) |
| Config / env | `src/core/config.py`; `TUTOR_DRAFT_MODEL`, doc 36 env table |
| Per-feature doc | `docs/services/chat-features/36-deep-tutor.md`, `42-author-diversity.md`, `45-query-planner-coverage.md` |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Tests | `tests/test_deep_tutor.py` |

No modal-card change (no stage added/removed). Confirm diagram still matches.

## Out of scope

- **Phase 3** — adaptive routing (complexity classifier in planner; per-route
  budgets, incl. routing simple Qs to nano draft to claw back latency).
- **Separate epic** — GraphRAG-lite (wire `concepts_kg` into tutor retrieval),
  decided after measuring whether the Phase-2 related-framings facet already
  closes the association gap.

## Success criteria

- Tests pass; new facet/diversity tests pass.
- Re-measured queries: steady draft latency, net tokens ≈ flat vs Phase-0.
- Bias-variance answer references framings beyond MSE when corpus supports it.
- Articulation + decomposition visibly improved on :5175; no LaTeX regression.
