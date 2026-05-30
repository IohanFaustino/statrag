# Deep-Tutor Efficiency — Phase 1: Token Cuts + Cheap Quality Wins

**Date:** 2026-05-30
**Status:** Approved (design)
**Branch target:** `feat/genai-ingest-deepseek` (or a dedicated `feat/tutor-phase1` branch)

## Background

Audit of the deep-tutor pipeline (`src/services/chat/agents/deep_tutor.py`,
2417 LOC) found a default request makes **6–8 LLM calls**:

| Stage | Model | Calls |
|---|---|---|
| `extract_concepts_ex` (query planner) | nano | 1 |
| `assess_coverage` | nano | 1 (+ retrieval re-query) |
| `build_synthesis_plan` | nano | 1 |
| `judge_image_candidates` | nano | 1–2 |
| draft (structured stream) | nano/deepseek | 1 |
| `build_vision_explanations` | gpt-4o-mini **vision** | **up to 3** |

Identified waste:
- **W1 — vision-explain**: default ON since 2026-05-20, up to 3 vision calls
  (image-input tokens) per question. Biggest single sink.
- **W2 — prompt bloat**: `DEEP_TUTOR_INSTRUCTIONS` ~440 lines (~3500 tok) sent
  every draft. So long the nano draft model loses instructions — the user's
  articulation/decomposition quality gaps are *adherence* failures, not missing
  rules.
- **W3 — coverage round-trip**: an extra serial nano call that re-reads the
  whole source bundle, even on simple questions.

Plus two cheap quality fixes:
- Citation `[N]` markers don't render as links when combined (`[1, 2]`,
  `[1]–[3]`) — frontend regex only matches single `^\[(\d+)\]`.
- Per-field word floors mis-tuned (tldr too long, applications too short).

Phase 1 is the low-risk, immediate net-efficiency slice. Model upgrade,
planner related-framings facet, adaptive routing, and GraphRAG-lite are later
phases/epics (see "Out of scope").

## Goal

Cut wasteful tokens with **zero quality regression** plus two cheap quality
wins. **No pipeline topology change, no model change** in this phase.

## Scope — five independent changes

### 1 · Vision-explain: cap 1 + lazy default

- **Artifact:** `src/services/chat/agents/deep_tutor.py` →
  `build_vision_explanations`; env; `docs/services/chat-features/36-deep-tutor.md`.
- **Change:** env `TUTOR_DEEP_VISION_EXPLAIN` becomes tri-state
  `{"0", "1", "lazy"}`, default `lazy`.
  - `1` → explain only the **single top-ranked figure** (was: all placed
    figures, up to 3).
  - `lazy` (new default) → emit no inline vision explanation; figure renders
    with caption + `judge_reason` (existing fallback). Reserve a frontend
    click-to-explain hook for a later phase (NOT built here).
  - `0` → unchanged (off).
- **Data flow:** function reads the env, selects `figures[:1]` when `1`, returns
  `{}` when `lazy`/`0`. Placement logic in `_convert_to_tutor_answer` already
  falls back to caption + judge_reason when no explanation is present — no
  change needed there.
- **Error handling:** unchanged — `asyncio.gather(..., return_exceptions=True)`;
  a failed/empty vision result is skipped, figure keeps caption fallback.
- **Token effect:** −2 vision calls in the typical multi-figure case; −1..3 when
  default flips to `lazy`.

### 2 · Prompt diet

- **Artifact:** `src/services/chat/prompts/deep_tutor.py` →
  `DEEP_TUTOR_INSTRUCTIONS`; `src/services/chat/tests/test_tutor_prompt_contract.py`.
- **Change:** de-duplicate, do **not** de-rule. The decomposition guidance
  (`### Bias`/`### Variance`/`### MSE`) is currently stated three times
  (`<task>` DEPTH block, the `definition` per-field block, and `<structure>`);
  the JSON math-escaping rule twice. Collapse each to one canonical block and
  reference it. Every *distinct* behavioral rule is preserved verbatim in
  meaning.
- **Data flow:** static string; no runtime change.
- **Error handling:** none.
- **Token effect:** ~−1200 input tokens per draft call.
- **Risk + mitigation:** trimming could drop a rule the model relies on →
  regression. `test_tutor_prompt_contract.py` asserts presence of each behavior
  and MUST still pass unchanged. Add a token-budget assertion
  (`len(DEEP_TUTOR_INSTRUCTIONS) < N`) to lock the diet against future creep.

### 3 · Coverage gate

- **Artifact:** `src/services/chat/agents/coverage.py` (or the call site in
  `deep_tutor.py`); env table in doc 36.
- **Change:** gate `assess_coverage` — run only when the answer genuinely needs
  it. `needs_coverage = len(facets) >= 4 or any("$" in f or "formula" in
  f.lower() for f in facets)`. Skip otherwise; log `coverage: skipped (simple)`.
- **Data flow:** pure-local predicate computed from the planner's `facets`
  before the nano call; no new I/O.
- **Error handling:** fail-safe toward quality — on any ambiguity (e.g. facets
  empty but sources thin), run coverage. Existing `assess_coverage` best-effort
  try/except is untouched.
- **Token effect:** −1 nano call (+ bundle re-read) on simple questions.

### 4 · Citation regex robustness

- **Artifact:** `web/src/components/views/TutorView.tsx` →
  `renderInlineWithCites`; `web/src/components/views/TutorView.*.test.tsx`.
- **Change:** replace the single-number branch `^\[(\d+)\]` with a matcher for
  comma/dash-separated lists and ranges:
  `^\[\s*\d+(\s*[,–-]\s*\d+)*\s*\]`. Expand the match into one citation
  pill per index, each linking to its existing `#cite-N` target, with the
  separator (`,` / `–`) rendered between pills.
- **Data flow:** tokenizer-level change in the existing while-loop; figure
  marker branch (`[F1]`) unchanged and still checked first.
- **Error handling:** malformed markers (`[1,]`, `[]`, `[1, x]`) fall through to
  literal text — current behavior preserved.
- **Token effect:** none (frontend only).

### 5 · Floor tuning (keep 6 fields)

- **Artifact:** `src/services/chat/prompts/deep_tutor.py` per-field word
  guidance; `src/services/chat/tests/test_deep_tutor.py` min-word assertions.
- **Change:** keep the six-aspect schema. Adjust word-count guidance strings:
  - `tldr` 60–110 → **45–90** (soften; it was padding simple answers).
  - `applications` 260–360 → **300–360** min (raise; user reports it runs short).
  - `example_intuition` keep 340–480.
  - Others unchanged.
- **Data flow:** prompt strings + schema docstring comments only.
- **Error handling:** none.
- **Token effect:** roughly neutral (shorter tldr offsets longer applications).

## Verification

After implementation:
1. `pytest src/services/chat/tests/test_deep_tutor.py
   src/services/chat/tests/test_tutor_prompt_contract.py` green.
2. `cd web && npm run test` (TutorView citation tests) green.
3. Restart backend; run one real query on **:5175**.
4. Open the tutor **(i)** modal — confirm the pipeline diagram is unchanged
   (no stage added/removed in Phase 1) and matches `docs/common ground/index.html`.
5. Confirm answer renders, combined citation markers now show as pills.
6. Compare token/cost in `retrieval_meta` + cost log before vs after on the same
   query; record the delta in the changelog.

## Interconnected artifacts touched (lockstep)

| Aspect | File |
|---|---|
| Backend logic | `agents/deep_tutor.py`, `agents/coverage.py` |
| Prompts | `prompts/deep_tutor.py` |
| Env flags | `TUTOR_DEEP_VISION_EXPLAIN` (tri-state), doc 36 env table |
| Frontend | `web/src/components/views/TutorView.tsx` |
| Per-feature doc | `docs/services/chat-features/36-deep-tutor.md` (+39 vision note) |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Tests | `tests/test_deep_tutor.py`, `tests/test_tutor_prompt_contract.py`, `web/.../TutorView.*.test.tsx` |

No modal-card (`tutorPipeline.ts` / `PipelineDiagram.tsx`) change in Phase 1 —
no stage is added or removed, only behavior within existing stages. Confirm the
diagram still matches after the change anyway.

## Out of scope (later phases)

- **Phase 2** — draft-model upgrade (nano → `deepseek-v4-pro`), query-planner
  **related-framings facet** (light association-breadth fix).
- **Phase 3** — adaptive routing (complexity classifier folded into planner;
  per-route budgets).
- **Separate epic** — GraphRAG-lite: wire the existing `concepts_kg` collection
  into deep-tutor retrieval. Decide *after* measuring `concepts_kg` density and
  whether the Phase 2 light fix already closed the association gap.

## Success criteria

- All existing tests pass; new tests for the five changes pass.
- Measured token/cost per question **down or flat** on a representative query.
- No visible answer-quality regression in the :5175 browser check.
- Citation pills render for combined/range markers.
