# 43 — Synthesis plan + evidence ledger (now the "Planner")

> 2026-05-21: this step is the **Planner** node — one call emits
> `SynthesisPlan = {thesis, contrasts, tasks}` (Synthesis-plan + Orchestrator are
> one agent). The earlier `outline`/`ledger` fields were removed: an open-keyed
> `dict` is invalid for OpenAI strict structured outputs and was silently 400'ing
> `build_synthesis_plan`. See [44-orchestrator-workers](44-orchestrator-workers.md)
> + changelog 2026-05-21.


## Why

The deep-tutor draft fills 7 aspect fields (Introduction, Definition, Formal
statement, Intuition, Examples, Trade-offs, Further reading) in **one** call.
Each field was improvised independently from the raw `<source_bundle>`, so the
answer read as disjoint pieces: no shared thesis, drifting facts/notation, and
the (now author-diverse) sources were blended rather than compared.

This step builds a plan **before** the draft and injects it, so the answer has a
single throughline and compares authors explicitly.

## What the plan contains

`SynthesisPlan` (`schemas/output.py`):
- `thesis` — one sentence the whole answer develops.
- `outline` — `aspect -> key points`.
- `ledger` — `LedgerClaim{ claim, author, source_rank, aspect }`: atomic,
  source-grounded claims tagged with the contributing author and the `[#rank]`
  they came from. The draft draws facts from here so fields stay consistent.
- `contrasts` — `AuthorContrast{ topic, author_a, position_a, author_b,
  position_b }`: only where sources genuinely differ.

## Flow

```
density_select → (figure judge ‖ build_synthesis_plan)  → draft
                          one structured nano call;        injects
                          parallel, ~max not sum           <synthesis_plan>/
                                                           <evidence_ledger>/
                                                           <contrasts>
```

`build_synthesis_plan` is best-effort: any failure returns `None` and the draft
proceeds on the legacy single-draft path. `DEEP_TUTOR_INSTRUCTIONS` has a
`<plan>` section telling the draft to follow the thesis, use the ledger's facts,
cross-reference aspects, and surface each contrast as a named comparison.

## Config

| Knob | Where | Default | Meaning |
|---|---|---|---|
| `stageModels.plan` | request | unset | `"off"` = skip (single-draft); a model id = enable with it; unset = env default |
| `TUTOR_SYNTHESIS_PLAN` | env | `1` | Master on/off when request leaves `plan` unset |

UI: **Synthesis plan** node in the About-model diagram (`tutorPipeline.ts` id
`plan`, between Figure-judge and Draft). Its dropdown = **Off (single-draft)** +
chat models, built with `NodeModelDropdown`'s `leadingOptions` prop. Selecting
"Off" sends `stageModels.plan = "off"` (A/B vs the current workflow); selecting a
model enables the step with that model. `_resolve_plan_model` resolves
`(enabled, model)`.

## Code

- `src/services/chat/schemas/output.py` — `SynthesisPlan`, `LedgerClaim`, `AuthorContrast`.
- `src/services/chat/prompts/deep_tutor.py` — `SYNTHESIS_PLAN_PROMPT`, `<plan>` section.
- `src/services/chat/agents/deep_tutor.py` — `build_synthesis_plan`,
  `_resolve_plan_model`, `_format_plan_block`, `_build_user_message(plan=)`,
  `_stream_draft(plan=)`, parallel `plan_task` in `run_deep_tutor`.
- Frontend — `NodeModelDropdown` (`leadingOptions`), `PipelineDiagram`,
  `tutorPipeline.ts`.

## Tests

`src/services/chat/tests/test_synthesis_plan.py` — model parse, `_resolve_plan_model`
(off/model/default), `_build_user_message` block injection, graceful failure.

## Notes / next steps

- The plan adds one nano call per turn (overlapped with the figure judge).
- Natural follow-ups: a coherence/Self-RAG reflection pass; a workflow-eval
  harness scoring coherence + distinct-author count + citation support to A/B
  `plan off` vs `plan on` quantitatively.
