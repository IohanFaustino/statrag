# 47 · Answer coherence — per-section rewrite

**Status:** ✓ Complete (2026-05-22) — Block A · Block B · Block C all shipped
**Common ground:** `docs/common ground/Elements/index.html` §10

## Problem

On "What is the bias-variance tradeoff?" the deep-tutor answer is factually correct but reads as seven disconnected mini-essays:

- **Definition** opens straight into bullets, no framing sentence saying what comes next; logical order is not bias → variance → tradeoff → graphic.
- **Formal statement** is emitted even when the sources contain no numbered theorem/definition.
- **Intuition** and **Examples** overlap.
- **Trade-offs and caveats** is generic, not grounded in corpus use-cases.
- Answers are short; the main draft path ran at an uncontrolled temperature.

Goal: a coherent, build-up narrative with explicit cross-references, plus larger and slightly more creative output. Shipped in three blocks.

## Blocks

| Block | Scope | Status |
|---|---|---|
| **A · params** | Draft size + temperature knobs | ✓ 2026-05-22 |
| **B · prompt content** | Definition framing+order, conditional Formal statement, Trade-offs→Applications | ✓ 2026-05-22 |
| **C · schema** | Merge `intuition`+`examples` → `example_intuition`; rename `trade_offs` → `applications`; formal omit-when-absent | ✓ 2026-05-22 |

## Block A — draft size + temperature (✓ 2026-05-22)

Tracing the draft calls in `agents/deep_tutor.py`: the OpenAI **structured** draft path (`beta.chat.completions.stream` / `.parse`) passed no `temperature` → model default (~1.0); only the deepseek router (`_stream_draft_via_router`) and the json last-resort used `0.2`.

Changes:
- `TUTOR_DEEP_MAX_TOKENS` default **2800 → 4000**.
- New `_DRAFT_TEMPERATURE` knob `TUTOR_DEEP_TEMPERATURE` (default **0.4**), applied to the structured stream, the router draft, and the json last-resort. Plan/extract/judge/coverage calls stay `0.0`.
- Reasoning-model guard: structured-stream carries the temp; `parse()` fallback omits it, so a temp-reject degrades structured → parse(no temp) → json instead of cascading to a 400.

Tests: `test_draft_knobs_defaults`, `test_draft_knobs_env_override` in `tests/test_deep_tutor.py`.

Env: see the table in `36-deep-tutor.md` (`TUTOR_DEEP_MAX_TOKENS`, `TUTOR_DEEP_TEMPERATURE`).

## Block B — prompt content (✓ 2026-05-22)

Prompt-only (`prompts/deep_tutor.py`) + heading rename; no schema change.
- (b) **Definition** (150-220w): opens with a framing sentence, builds up component-by-component (bias, then variance) before the tradeoff, ends with a graphical hand-off when a figure is attached.
- (c) **Formal statement**: conditional — only when a numbered/labelled statement exists in sources ("Conforming to Definition X.Y.Z, …" + verbatim blockquote); else empty string. Heading dropped by `assemble_markdown`. Old "INDIRECT WHEN NOT" self-write fallback removed. (Invariant 22.)
- (e) **Trade-offs → Applications**: `ASPECT_HEADINGS["trade_offs"]` = "Applications"; corpus-grounded use-cases grouped by domain, invent-nothing. Synced: `App.tsx` heading map + `tutorMode.ts` mode description.

Verified live on bias-variance (econometrics corpus): Definition framing + build-up present; Formal statement empty → heading absent; Applications grouped Econometrics / Nonparametric smoothing (corpus-real). Tests: 4 contract tests (3 new + 1 updated), heading-list updated. The schema KEY stays `trade_offs` until Block C.

## Block C — schema (✓ 2026-05-22)

Answer is now a 6-aspect set: `tldr, definition, formal_statement, example_intuition, applications, further_reading`.
- **Merge** `intuition` + `examples` → `example_intuition` ("Example & Intuition"): three cases → analyse the three → literal "The intuition here is that …". Touched: prompt, `DeepTutorAnswer`, `ASPECT_HINT`, `ASPECT_HEADINGS`, `image_judge` hint enum + per-aspect descriptions, `App.tsx` heading map, `tutorMode.ts` description, and the example-relevance audit (`_score_example_relevance`/`_embed_relevance` now score `example_intuition` vs definition+formal_statement).
- **Rename** `trade_offs` → `applications` everywhere (schema key + all of the above). `coverage.py`/`orchestrator_workers.py` were checked — they do NOT reference aspect keys, so retrieval/coverage logic is untouched (rag-verify not triggered).
- Formal omit-when-absent confirmed render-side; all fields stay required (strict-safe). Invariant 22.

Verified live + browser on :5175 (bias-variance): headings Introduction → Definition → Example & Intuition → Applications → Further reading; Formal statement absent; example_intuition showed the three-case → analysis → "The intuition here is that …" structure; Applications grouped by domain. New schema accepted by OpenAI structured output (no 400/fallback). 544 backend / tsc / 39 vitest green.

### Follow-up (not blocking)
- `data/eval/image_label_set.csv` may carry the old `examples`/`trade_offs` aspect labels; the `quality_images`-marked `test_image_judge_quality.py` (deselected by default) will need its label set re-mapped to `example_intuition`/`applications` before that suite is run.
