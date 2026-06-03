# Facilitate mode — reasoning/CoT refinement (map + teach)

**Date:** 2026-06-03
**Status:** design — pending experiment + user approval
**Scope:** facilitate mode only (`src/services/chat/agents/facilitate.py`). Resume/tutor/qa untouched.

## Problem

Facilitate's **map** stage (concept map: `key_points` + `concepts`) and **teach** stage
(the simplify rewrite into clear prose + key points with `[[cN]]` anchors) commit to
output in a single shot with no space to reason. This yields avoidable misses:
weak concept selection (boxing notation or central-definition formulas it shouldn't),
duplicated key points, and lessons that drift from the no-repeat / one-idea-per-paragraph
rules. Goal: give both stages a hidden chain-of-thought scratchpad to refine results,
measure whether it actually helps before shipping.

## Approach (decided)

Add a **hidden reasoning field** to each stage. The model writes terse reasoning *first*,
then emits the real fields. The reasoning is parsed off and discarded — never rendered,
never stored. One LLM call per stage (no latency-doubling two-pass, no model swap).

### Map stage
- `FacilitateMap` gains `reasoning: str` as its **first** field.
- `FACILITATE_MAP_PROMPT` (reasoning variant) instructs: first reason about the section's
  core teaching unit, which formulas truly merit their own modal (not the central
  definition formula, not bare inline expressions), and which concepts are near-duplicates
  to merge; *then* fill `key_points` and `concepts`.
- Parser is unchanged (`data.get("key_points")` / `data.get("concepts")`); `reasoning` is ignored.

### Teach stage
- New schema `FacilitateTeachOut{reasoning: str, body: str}` (teach currently returns raw markdown).
- `FACILITATE_TEACH_PROMPT` (reasoning variant) instructs: first plan the lesson
  (hook → one paragraph per distinct idea → example placement → which `[[cN]]` anchor goes
  where → explicit no-repeat check); *then* write `body`. JSON escaping carries markdown + LaTeX.
- Runner parses `body`, drops `reasoning`. Fallback on parse error keeps today's behavior.

### Toggle
Single env flag `FACILITATE_REASONING` (default `0`). On → map + teach use the reasoning
prompts + schemas. Off → byte-identical to today. Lets the experiment and any later A/B run
without forking the runner. Final default decided from experiment results.

## Experiment (run before any system change — eval-only)

New `src/services/chat/eval/facilitate_reasoning_eval.py`, mirroring the existing
`facilitate_eval.py` (manual `-m facilitate_reasoning` marker, live API). It swaps prompts/
schemas locally and does **not** modify the shipped pipeline.

- **Corpus:** Hansen `ch07`, sections §7.2–7.5.
- **Variants:** `baseline` (reasoning off) vs `reasoning` (map + teach on).
- **Runs:** 3 per variant per section.
- **Judge:** `settings.openai_model_nano` (same as existing eval), LLM-as-judge 1–5 on
  clarity, faithfulness, keypoint_coverage, non_expansion, concept_id.
- **Output:** `docs/superpowers/eval/2026-06-03-facilitate-reasoning.md` — ranked score
  table + 1–2 side-by-side sample bodies (numbers + real text).

## System integration (only if approved)

Lockstep artifacts to change when shipping:

| Artifact | Change |
|---|---|
| `schemas/output.py` | `FacilitateMap.reasoning`; new `FacilitateTeachOut` |
| `prompts/chapter.py` | reasoning variants of MAP + TEACH prompts |
| `agents/facilitate.py` | flag read; teach parses JSON body; reasoning stripped |
| `docs/services/chat-features/` | env table row for `FACILITATE_REASONING` + per-feature note |
| `docs/system/invariants.md`, `changelog.md` | note the new optional stage behavior |
| tests | `test_facilitate.py` — reasoning on/off parse + strip; fallback path |

Modal card (`tutorPipeline.ts` / `ChapterPipelineDiagram.tsx`) **unchanged** — no new
visible stage; map/teach nodes keep their labels.

Default-ON vs default-OFF is decided from the experiment scores + sample quality.

## Non-goals (YAGNI)

- No two-pass / separate reasoning call. No thinking-model routing.
- No resume/tutor/qa changes. No frontend changes. No new request knobs (env-only toggle).
- Reasoning is never surfaced to the user or persisted.
