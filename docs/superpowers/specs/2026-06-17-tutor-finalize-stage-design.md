# Tutor finalize+verify stage + render/figure fixes — design

**Date:** 2026-06-17
**Status:** approved (brainstorming) — pending writing-plans
**Mode:** deep-tutor

## Problem

Live tutor answers fail in three ways (user-reported, queries like *"What is
stationarity and its versions?"*, *"What is stationarity? What are its
versions? What is a unit root?"*, *"What is the KPSS and ADF test of
stationarity?"*):

1. **Formatting** — KaTeX render errors; too many bare inline formulas
   (`\rho=1`) with no surrounding explanation; multiple definitions crammed
   into one box instead of one box per definition; inline math overlapping
   the box border; image-retrieval error on the KPSS/ADF query.
2. **Completeness** — multi-question prompts get only partially answered; the
   answer doesn't weave all sub-questions (stationarity → versions → unit
   root) into one storytelling arc.
3. The user's hypothesis: a stronger model should *finalize* the workflow and
   mount the final response, and also verify all elements (images, KaTeX) work.

## Root-cause attribution (ground-truth inspected)

The symptoms live on **three different layers** — a stronger model only fixes some:

| Symptom | True layer | Fixed by |
|---|---|---|
| Multiple defs in one box / sub-questions dropped | model + schema/prompt | **stronger finalizer** (C1) |
| KaTeX errors / inline overlaps box | frontend render (`TutorView.tsx`, `tutor.css`) | **CSS + tokenizer fix** (C3) |
| Image-retrieval error (KPSS/ADF) | retrieval / figure-judge | **diagnose + fix at source** (C4) |

Key fact: the **final answer is currently mounted by `nano`** — the single
narrative-draft call defaults to `settings.openai_model_nano`
(`deep_tutor.py:915`, `_resolve_stage_model("draft", …)`). That is the weakest
model in the pipeline writing the user-facing answer.

## Decisions (user-approved)

- **New finalize+verify pass** (not "just upgrade the draft model", not
  "no new model").
- **Quality first** — extra latency/cost per answer is acceptable.
- **Model chosen by bake-off**: deepseek-v4-pro vs gpt-5.4 vs gemini-3-pro on
  the real failing queries; winner becomes the default.
- **Draft runs silent; finalizer streams** — the user sees one clean, complete,
  correctly-formatted answer appear (slightly later first token).
- C4 (image bug) folded into this spec.

## Design

### C1 — Finalize+verify stage (the feature)

New stage in `deep_tutor.py`, after the narrative draft, before
`_convert_to_tutor_answer`.

- The cheap `nano` draft runs **non-streamed** (silent) to produce raw
  material (aspects + citations).
- A **strong finalizer model streams the user-facing answer**, receiving:
  draft aspects, `sources`, planner `facets[]`, and approved figures, under
  the existing `DeepTutorAnswer` structured-output contract.
- The finalizer prompt enforces:
  - **(a) every facet / sub-question answered** — `facets[]` already produced
    by the query planner; the finalizer must address each, woven into one
    narrative arc (fixes completeness).
  - **(b) one formal statement per `formal_statements[]` entry** — the render
    path already supports the array; emitting one entry per definition makes
    "one box per def" true-by-construction (fixes the crammed-box symptom).
  - **(c) clean math delimiters + every bare formula carries explanation**
    (no orphan `\rho=1`).
- **Streaming**: the finalizer emits the same per-aspect / `structured_output`
  SSE events the draft used to emit, so the frontend SSE contract is unchanged.
- **Wiring**: env `TUTOR_FINALIZE` (on/off, default on once shipped) +
  `TUTOR_FINALIZE_MODEL` + `stageModels["finalize"]`. Model resolved via the
  existing `_resolve_stage_model("finalize", …)`.

### C2 — Pure-code verify guards (lean; mirrors `seam_guard`)

After the finalizer, pure code (no extra model call):

- **Drop broken `[Fn]` figures** — validate each referenced figure resolves to
  a real image URL; strip refs that don't (neutralizes the image-error symptom
  at the answer layer even before C4 lands).
- **Log missing facets** — check each `facet` keyword is present; on a miss,
  **log it** (no auto-redraft yet — YAGNI; add redraft only if logs prove the
  finalizer drops facets in practice).

### C3 — Render-layer fixes (frontend, no model)

- `.tutor-view__quote` (`tutor.css:100`): add `overflow-x:auto; min-width:0`
  so wide inline KaTeX clips instead of overlapping the box border (the box has
  no `overflow-x` today, unlike `.tutor-view__math-block`).
- **KaTeX errors**: diagnose live first (`debug_Advisor`), then fix the
  specific `normalizeMathDelimiters` / tokenizer gap that's actually firing —
  not a speculative rewrite.

### C4 — Image-retrieval bug (retrieval layer)

- Root cause unknown → `debug_Advisor` + live repro on the KPSS/ADF query to
  localize (`fetch_image_candidates` / `resolve_image_for_vision` throwing, or
  a broken URL). Fix at source. C2's guard is belt-and-suspenders.

### C5 — Finalizer bake-off (decides the model)

- Manual A/B/C of deepseek-v4-pro / gpt-5.4 / gemini-3-pro as the finalizer on
  the two failing queries, scored on sub-question completeness + LaTeX
  consistency + box structure. The eval set **is** those two queries — no
  variance harness.
- **Flag**: `gemini-3-pro` is not in the router registry (only `gemini-2.5-flash`
  / `gemini-2.5-pro`), but routing is by `"gemini"` prefix
  (`router.py:258/332`), so it should still route for an offline run — verify
  reachable before relying on it; fall back to `gemini-2.5-pro` if not.

## Lockstep artifacts (per CLAUDE.md)

Backend logic (`deep_tutor.py`) · prompts (`prompts/deep_tutor.py`) · env table
+ new feature doc `docs/services/chat-features/58-tutor-finalize.md` + mermaid
node in `36-deep-tutor.md` · modal pipeline node (`web/src/data/tutorPipeline.ts`
+ `PipelineDiagram.tsx` + test) · HTML `docs/common ground/Elements/modes/tutor.html`
· `docs/system/invariants.md` + `changelog.md` · tests
(`src/services/chat/tests/test_deep_tutor.py` + frontend render test).

## Amendment (2026-06-17, post-bake-off) — two finalizer routes, same output, frontend-distinguishable

The bake-off found only `gpt-5.4` produced valid finalizer output out of the box;
`deepseek-v4-pro` returned unparseable JSON and `gemini-3-pro` was unreachable
(`gemini-2.5-pro` fallback failed). User decision: **support BOTH routes** rather
than pick one model.

- **Route A — structured** (OpenAI gpt family, `is_structured_output_capable` True):
  `_stream_structured`, strict json_schema. Works today.
- **Route B — tolerant** (deepseek / gemini / qwen / groq, capability False):
  `_stream_draft_via_router` — json_object + `_loads_tolerant_json_object` +
  `skip_format_checks`. **Must be hardened** so these models reliably yield a
  valid `DeepTutorAnswer` (confirm deepseek thinking is disabled on this path;
  ensure tolerant parse salvages chatty/partial payloads). Localize the current
  failures with the bake-off repro before fixing.
- **Same output contract:** both routes return `(DeepTutorAnswer, aspects)` and
  feed the identical downstream (`_verify_finalized` → `_convert_to_tutor_answer`).
- **Frontend-distinguishable:** the SSE meta carries the finalize model + route
  (`finalizeModel`, `finalizeRoute`) so the modal (Task 7) shows which finalizer
  produced the answer.
- **Default model:** `gpt-5.4-2026-03-05` (the reliable route-A model); other
  models selectable via `TUTOR_FINALIZE_MODEL` / `stageModels["finalize"]` and
  served by route B.

## Out of scope

- Auto-redraft on missing facet (C2 logs only until proven needed).
- Any retrieval change beyond fixing the C4 image bug.
- Touching QA / facilitate / resume modes.
