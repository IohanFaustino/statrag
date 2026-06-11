> **SUPERSEDED 2026-06-11** by [57-tutor-narrative](57-tutor-narrative.md) — orchestrator-workers / organize / deepagents synthesis removed; tutor now uses a single woven-narrative synthesizer.

# 44 — Orchestrator-workers drafting workflow (per author)

## Why

The single draft (and the plan-and-write "Synthesis plan" step) writes all 7
aspects in one call. For multi-author questions that under-uses the diverse
sources. The **orchestrator-workers** pattern (Anthropic, "Building Effective
Agents") decomposes the task, runs **parallel worker LLMs**, and a
**synthesizer** integrates — giving each author a deep, separately-attributed
treatment that the synthesizer then compares.

This workflow splits **per author** and is **selectable** (default stays the
cheaper single-draft path).

## Flow

```
density_select → diversity → synthesis plan
   → tutorWorkflow == "orchestrator":
        tasks = plan.tasks   (the Planner already decided them — ONE agent, no 2nd call;
                              empty → per-author fallback via diversity.author_key)
        ‖ run worker per task  → AuthorBrief{summary, key_points, source_ranks}
        → synthesizer (streamed): DEEP_TUTOR_INSTRUCTIONS + SYNTHESIZER_ADDENDUM
          consumes <author_briefs> + plan + source bundle → DeepTutorAnswer
   → tutorWorkflow == "single" (default): the existing single draft
```

The **orchestrator is the Planner LLM** (`build_synthesis_plan`,
`SYNTHESIS_PLAN_PROMPT`) — the same call that produces thesis/contrasts also
emits `tasks`, *dynamically deciding* the subtasks per question. That dynamic
decomposition is what makes it orchestrator-workers rather than fixed
parallelization (Planner + Orchestrator are one agent). Only the synthesizer
streams (workers run before it, parallel via `asyncio.gather`). Fallbacks:
orchestrator declines/fails → per-author split; <2 usable subtasks/briefs →
single draft (`run_orchestrator_workers` returns `(None, {})`).

The modal pipeline diagram is **workflow-aware**: selecting "Orchestrator"
redraws the draft region into `Orchestrator → Worker ×N (parallel) →
Synthesizer` (see `PipelineDiagram.tsx`, `docs/common ground/index.html`).

## Config

| Knob | Where | Default | Meaning |
|---|---|---|---|
| `tutorWorkflow` | request | `null` | `"single"` or `"orchestrator"`; null → env default |
| `TUTOR_WORKFLOW` | env | `single` | Default drafting workflow |
| `TUTOR_WORKER_MODEL` | env | nano | Worker model (synthesizer uses the Draft-node model) |

UI: **Drafting workflow** node in the About-model diagram (`tutorPipeline.ts` id
`drafting`, between Synthesis plan and Draft), a `NodeChoiceDropdown` with
`Single draft` / `Orchestrator (per author)`. Plumbed `App.tutorWorkflow` →
`useChat` → POST body. Cost: N worker calls (N = #authors) + 1 synthesizer.

## Code

- `src/services/chat/agents/orchestrator_workers.py` — grouping, worker,
  orchestrator.
- `src/services/chat/agents/deep_tutor.py` — `_stream_structured` (shared
  stream loop), `_resolve_workflow`, `_draft_coro` branch + fallback.
- `src/services/chat/prompts/deep_tutor.py` — `AUTHOR_WORKER_PROMPT`,
  `SYNTHESIZER_ADDENDUM`.
- `src/services/chat/schemas/output.py` — `AuthorBrief`.
- Frontend — `tutorPipeline.ts`, `PipelineDiagram.tsx`, `NodeChoiceDropdown.tsx`.

## Tests

`src/services/chat/tests/test_orchestrator_workers.py` — grouping, worker
graceful failure, fallback (<2 authors / all-fail), `_resolve_workflow`, brief
formatting.

## Notes

- Reuses the synthesis plan as the orchestrator's shared context (thesis +
  contrasts); the per-author worker split is the new decomposition.
- Possible follow-ups: per-aspect or orchestrator-dynamic decomposition; a
  workflow-eval harness to score single vs orchestrator quantitatively.
