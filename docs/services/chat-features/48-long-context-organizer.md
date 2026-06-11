> **SUPERSEDED 2026-06-11** by [57-tutor-narrative](57-tutor-narrative.md) — orchestrator-workers / organize / deepagents synthesis removed; tutor now uses a single woven-narrative synthesizer.

# 48 · Long-context organizer + real application cases

**Status:** ✓ Complete (2026-05-22)
**Common ground:** `docs/common ground/Elements/index.html` §11 · follows [47-answer-coherence](47-answer-coherence.md)

## Problem

After §10, two residual gaps on "What is the bias-variance tradeoff?":
1. **Definition gave no formulas** for bias/variance, and never defined **MSE** — even though the figure is built on the MSE decomposition. Root cause: §10 Block B told `definition` to defer formulas to `formal_statement`, but that field is empty when no numbered theorem exists → formulas had no home. MSE was never a facet (it only surfaces via the figure, and coverage runs before the image judge).
2. **Applications listed generic domain labels**, not real cited cases — retrieval was concept-centric and the prompt accepted labels.

User direction: stop leaning on a narrow per-facet draft — retrieve a large pool and let **DeepSeek V4-PRO** organize the coherent pieces into the fields. **Augment, not replace.**

## Block D — long-context organizer + formula-home fix

- **Formula home (all draft modes):** `definition` MUST write each component's formula in LaTeX + the central decomposition (e.g. `MSE = bias² + variance + σ²`) inline, including a central quantity (MSE) present in the sources/figure even if absent from the question. Not deferred to `formal_statement`. (Invariant 23.)
- **`organize` drafting workflow:** third option beside `single`/`orchestrator`.
  - `_build_organize_pool(query, candidates, ranked, max_tokens)` — reranks the wide pool to `TUTOR_ORGANIZE_POOL` (60), puts the density-ranked sources first (figure-aligned), trims to `TUTOR_ORGANIZE_MAX_TOKENS` (120k, ≈ chars/4); actual tokens logged.
  - Routed to `TUTOR_ORGANIZE_MODEL` (default `deepseek-v4-pro`) via `_stream_draft(..., model=organize_model, instructions=ORGANIZER_PREAMBLE + DEEP_TUTOR_INSTRUCTIONS)`.
  - **Augment:** density-rank still runs → author-diversity + figure co-location unaffected. Coverage stays (optional).
  - Best-effort: organize→single fallback. Router parse hardened — salvages partial payloads (fills missing aspect keys), falls back cleanly on empty output.
- Frontend: `tutorWorkflow:"organize"` request literal; `PipelineDiagram` workflow dropdown option "Organize (V4-PRO, long-ctx)"; `tutorPipeline.ts` drafting node desc.

Env: `TUTOR_ORGANIZE_MODEL`, `TUTOR_ORGANIZE_MAX_TOKENS` (120000), `TUTOR_ORGANIZE_POOL` (60), `TUTOR_WORKFLOW=organize`.

## Block E — real application cases

- Planner (`EXTRACT_CONCEPTS_BUDGET_PROMPT`) always emits an application-case facet + query, so the pool contains real cases for the draft/organizer to find.
- `applications` prompt requires a cited SPECIFIC case (named method/model/dataset/study/worked example), forbids bare domain labels, honest "no concrete applied case" fallback.

## Verification (2026-05-22)

Live, default path (bias-variance): Definition now renders bias `$\mathbb{E}[\hat\theta-\theta]$`, variance `$\mathrm{var}(\hat\theta)$`, and the MSE decomposition; Applications cites James et al. (U-shape/double-descent) and Wooldridge's estimator comparison — real cases, not labels.

Tests: 6 contract/unit guards (see changelog). 549 backend / tsc / 39 vitest green.

## Honest caveats

- **`deepseek-v4-pro` is not a reachable model in this environment** (forward-dated id). The organize path streamed empty and fell back to the single draft (complete, correct answer). So `organize` is implemented + safe but **not exercised end-to-end** here. Its real context window is unverified — hence the token-budget guard, never assuming 1M.
- **`rag-verify` FAILS on invariant 2** (`page_from=-1`, 28/50 sampled `introduction_textbooks` points) — a PRE-EXISTING ingestion condition, NOT caused by §11 (which never touches ingestion). Needs a separate ingestion fix.
