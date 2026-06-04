# Plan D — Productionize L3b (deepagents + synthesis skill) in the live tutor

**Date:** 2026-06-04
**Status:** ⏳ PENDING — draft for review before building (do NOT implement until approved).
**Builds on:** Plan C verdict (`docs/superpowers/eval/2026-06-04-ow-deepagents-compare.md`) —
**L3b won**: deepagents + a written synthesis `SKILL.md` beat the current synthesizer on
all 6 questions (quality 4.39 vs 3.96, fidelity 4.50 vs 3.39) at ~$0.0046/answer. L4
(subagents) rejected.

## Goal

Make L3b usable in the running app at **:5175**: wire `synthesize_with_skill` into the
orchestrator-workers stage behind a flag, turn its **free-text** output into a renderable
**`DeepTutorAnswer`**, handle its **~30–57 s blocking** latency in the chat UX, add
`deepagents` as a real dependency, and **browser-verify on :5175**.

## What already exists (Plan C, committed on `feat/ow-harness-planc`)

- `src/services/chat/agents/ow_deepagents.py` → `synthesize_with_skill(query, sources,
  briefs) -> (text, in_tok, out_tok)` (the winner).
- `src/services/chat/agents/ow_skills/synthesis/SKILL.md` (the winning skill).
- `run_orchestrator_workers` already dispatches `TUTOR_OW_HARNESS=3` to *bare* deepagents
  (`synthesize_with_deepagents`) with L0 fallback. L3b is NOT yet wired.

## The three hurdles + recommended resolutions (confirm at review)

### 1. Schema integration (the hard one)
L3b returns free text; the frontend renders a structured `DeepTutorAnswer`
(`tldr / definition / formal_statement / example_intuition / applications /
further_reading` + citations + math). **Recommended:** a follow-on **nano "schema-fill"
pass** — after L3b produces the synthesis text, one structured-output nano call maps that
text into the `DeepTutorAnswer` schema (reuse the existing structured-synth path /
`_stream_structured`). This preserves L3b's measured quality (the deepagents agent does the
hard synthesis) and yields renderable, streamable output, for one extra cheap nano call.
*Alternative (open):* make the deepagents agent emit the schema JSON directly via a submit
tool — fewer calls but unproven and risks losing the quality the free-text run measured.

### 2. Latency + streaming
L3b is **blocking ~30–57 s** (`agent.invoke`), vs the current synth which streams aspects.
**Recommended:** ship L3b as **opt-in** (a "deep synthesis (slower)" toggle / per-request
`tutorWorkflow`), NOT default; keep the streaming L0 synth as default. The schema-fill pass
(hurdle 1) streams the final `DeepTutorAnswer` so the user sees the answer render once it
lands. Show a "synthesizing across authors… (~45 s)" progress state. *Open:* accept blocking
vs invest in true deepagents streaming.

### 3. Flag + deps + lockstep
- New harness level for the skill arm (e.g. `TUTOR_OW_HARNESS=5` = "deepagents + skill")
  wired into `run_orchestrator_workers` → `synthesize_with_skill` → schema-fill →
  `DeepTutorAnswer`, with L0 fallback on any failure.
- Add `deepagents` (+ its langchain/langgraph minor bumps, already in-pin) to
  `requirements.txt`.
- Lockstep: modal card (`web/src/data/tutorPipeline.ts` orchestrator node note), env table
  (doc 36), per-feature doc (doc 55 / new doc 56), invariants, changelog, tests.
- **Browser-verify on :5175:** ask a fan-out question with the flag on; confirm the
  deepagents-skill synthesis renders as a proper `DeepTutorAnswer` (all fields, citations,
  math) and the latency UX is acceptable.

## Acceptance criteria

1. Flag on → a fan-out tutor question returns a fully-populated `DeepTutorAnswer` produced
   by L3b, rendered correctly at :5175.
2. Flag off (default) → byte-for-byte current behavior; any L3b failure (deepagents missing,
   429, empty, schema-fill fail) falls back to L0.
3. Full chat suite + web tests green; `deepagents` import-guarded so its absence never
   breaks default paths or CI.
4. Latency UX: the long synth shows progress, does not look hung.

## Out of scope

- L4 (subagents) — rejected by Plan C.
- Model sweep / non-nano synth — separate phase.
- Making L3b the default — it stays opt-in until latency is acceptable for all users.

## Open decisions for review (tomorrow)

- Schema-fill nano pass vs direct-JSON deepagents tool (hurdle 1).
- Opt-in toggle vs accept-blocking-default (hurdle 2).
- Level numbering / request knob name (hurdle 3).

## Next step

On approval → `writing-plans` for the Plan D implementation plan, then subagent-driven
(Sonnet) execution on a fresh branch off the merged stack. The Plan C branch
(`feat/ow-harness-planc`, with planb stacked) should be merged to main first.
