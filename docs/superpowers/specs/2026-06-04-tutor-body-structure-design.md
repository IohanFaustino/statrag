# Tutor answer — in-body text structure (C-style) + math/figures in Example

**Date:** 2026-06-04
**Status:** design (awaiting review)
**Scope:** deep-tutor pipeline — drafting/synthesis prompt + L3b deepagents synthesis skill. No section/subsection layout change, no frontend schema change.

## Problem

Tutor answers (e.g. conversation `2196374d…`, "Data Generating Process in a time series") render each `###` subtopic as one **dense monoparagraph**. Hard to scan. The figure machinery and math machinery exist but the prose is a wall of text.

Root cause: `src/services/chat/prompts/deep_tutor.py` lines ~309-321 **mandate** prose and **forbid** bullets:

> "Use … `###` SUBSECTION HEADERS …, NOT bullet lists. Each `### Subheader` … followed by a SUBSTANTIVE paragraph of 3-5 sentences … Do NOT use `- ` bullet lists for the main structure."

## Goal (approved via visual mockups)

Keep `##` sections and `###` subsections **exactly as today**. Change only the **body prose inside each subtopic** to the approved **Option C** treatment:

- A short **bold lead sentence** opening the subsection.
- **Bold lead-in bullets**, one claim per line, citations `[n]` at line end.
- **Display math** `$$…$$` placed **inside the pertinent subtopic** (esp. each Example case), inline `$…$` for short expressions — never piled at the end.
- **Figures**: each Example case that has an approved figure carries the `$$formula$$` and the `[Fn]` marker in-body, resolving to a real figure card.

Argument-heavy lines may stay as a short sentence; bullets are for the enumerable/claim parts. Not every line must be a bullet.

## Non-goals (YAGNI)

- No new response-schema field, no new frontend block type. `TutorView` already parses `**bold**`, `- bullets`, `$…$`/`$$…$$`, `![alt](url)`. Frontend untouched.
- No change to `##`/`###` structure, headers, or the Sources panel.
- No modal/pipeline-diagram change (no stage added/removed) → `tutorPipeline.ts` / `PipelineDiagram.tsx` untouched.
- Do not rebuild the figure pipeline. It works; we only ensure the prompt emits markers in the right place and verify attach fires on the OW path.

## Changes (artifacts in lockstep)

### 1. Draft/synth system prompt — `src/services/chat/prompts/deep_tutor.py`
Rewrite the "no bullets / 3-5 sentence paragraph" block (~309-326):
- Replace the bullet ban with the C rule: each `###` subsection = one bold lead sentence + bold-lead-in bullets (claim per line), citations inline at line end.
- Keep `###` headers ≤6 words, no trailing colon; keep DEPTH-OVER-BREVITY (bullets carry the same substance, not one-liners).
- `<math_format>`: add an explicit placement rule — display math goes **inside the subsection it belongs to**, especially each Example `### Case` subsection; never collect at the end.
- `<figures>`: strengthen — an Example case with an approved figure should state the `$$formula$$` and carry the `[Fn]` marker in the same subsection.
- Per-aspect format map (definition/applications/example/further_reading): update so each aspect's `###` subsections use the C body, not prose paragraphs.

### 2. L3b deepagents synthesis skill — `src/services/chat/agents/ow_skills/synthesis/SKILL.md`
The deepagents synthesizer (`synthesize_with_skill`, model `settings.openai_model_nano` = `gpt-5.4-nano`) writes the free-text synthesis that `_schema_fill` re-expresses. Add to SKILL.md Instructions:
- Body structure: bold lead sentence + bold-lead-in bullets per subtopic.
- Math: keep `$…$`; add `$$…$$` for display, placed with the point it supports.
- Figures: keep any `[Fn]` markers from the briefs in the subsection they belong to.
So the synthesis text already carries C-structure before schema-fill.

### 3. Verify schema-fill preserves structure — `src/services/chat/agents/ow_deepagents.py` / `deep_tutor.py`
`_schema_fill` re-expresses synthesis into the `DeepTutorAnswer` schema via the same draft system prompt. Change 1 covers it; add a test asserting bullets/`$$`/`[Fn]` survive the fill.

### 4. Verify figure attach on the OW-deep path
Confirm the figure judge/attach (`_choose_target_aspect`, `_build_lead`, figures array fill) runs when `tutorWorkflow="orchestrator-deep"` and a relevant image exists, so `[Fn]` → populated `figures[]`. If it does not fire, fix the wiring (not a rebuild). Document the finding either way.

## Model

Subagent/synthesis model stays `settings.openai_model_nano` (`gpt-5.4-nano-2026-03-17`, $0.20/$1.25 — already the repo default and the OW worker/synth default). There is no "GPT-4.5-mini"; the only cheaper OpenAI small is `gpt-4.1-nano` ($0.10/$0.40), not adopted here — nano-5.4 already governs these stages and gives better structured-formatting adherence. No model change required.

## Testing

- `src/services/chat/tests/` — new/updated test: given fixed briefs + a figures bundle, the drafted/synth answer body contains `- ` bullets with `**bold**` lead-ins, at least one `$$…$$` inside an Example `### Case`, and the `[Fn]` marker in that case; `citations` still match `[n]`.
- Schema-fill test (Change 3): C-structure survives the re-express.
- Regression: existing deep_tutor / OW tests stay green.
- Manual: run the DGP question through `orchestrator-deep` on :5175, confirm bodies are C-style and a figure card renders when a figure matches.

## Docs lockstep (CLAUDE.md rule)

- `docs/system/invariants.md` — update the body-format invariant (prose → C bullets).
- `docs/system/changelog.md` — entry.
- `docs/services/chat-features/56-deep-synthesis-l3b.md` (+ `36-deep-tutor.md` if it states the body format) — reflect C body + math placement + figure-in-Example.
- No `tutorPipeline.ts` / modal change (no stage change).
