# Orchestrator-Workers Harness-Level Ablation — Design

**Date:** 2026-06-04
**Status:** approved (design)

## Goal

Take ONE coordination-heavy deep-tutor stage — **orchestrator-workers** — and test it
across four harness levels (none → increasing deepagents/LangSmith features), holding
the model constant, to learn **whether a harness improves the inter-model context
handoff and the answer quality, and at which level the added complexity pays off.**
This is the first pilot of a larger sequential program (organize and planner-chain
follow). It also produces a reusable eval-flow methodology so later stage-ablations
are turnkey.

North star: **upgrade context handling between models** (today: ad-hoc strings) and
**improve output quality**, with cost/latency measured so we only keep what earns its
place.

## Background — the current handoff

`src/services/chat/agents/orchestrator_workers.py`: the orchestrator groups sources by
author and runs one worker LLM per author (parallel), each emitting an `AuthorBrief`.
`_format_author_briefs(briefs)` **flattens those briefs into a single string**, which
the synthesizer reads to produce the final `DeepTutorAnswer`. The brief→synthesizer
handoff is a flat string — the exact "context handling between models" we want to
upgrade. Falls back to single-draft when < 2 authors or all workers fail.

## The four harness levels (the ablation)

All gated by one env flag `TUTOR_OW_HARNESS` (`0` default). Any level failure logs and
**falls back to L0**. Model is held constant across all levels (nano workers + the
current synthesizer model) so measured differences are the **harness's** effect only.

| Level | Flag | Added capability | Brief→synthesizer channel |
|---|---|---|---|
| **L0 baseline** | `0` | none (current code) | `_format_author_briefs` → flat string |
| **L1 observability** | `1` | LangSmith tracing wrapped on orchestrator/workers/synthesizer; **no behavior change** | same string, now *measured* (content, tokens, dropped facts) |
| **L2 structured context** | `2` | deepagents shared **virtual filesystem / state**: each worker writes its brief as a structured entry; synthesizer reads structured entries, not a flattened blob | structured FS/state channel |
| **L3 full deepagents** | `3` | deepagents **planning + spawned subagents (one per author) + memory**, replacing the hand-rolled orchestrator | deepagents end-to-end |

L1 is pure measurement (safe, behavior-identical). L2 changes only the handoff data
structure. L3 changes the orchestration engine. Increasing risk/complexity by level —
the point is to find where the curve stops paying.

## Feasibility spike (Task 1 — a hard gate)

`scripts/spike_deepagents.py` (throwaway, not committed to prod deps): `pip install
deepagents` into the venv, build a trivial 2-subagent example using the shared
filesystem, and **confirm deepagents can drive our router models** (nano via
`aclient_for`/OpenAI-compat) — not only LangChain `ChatModel` objects. Capture: does it
run on `langgraph>=1.0`? what is the model-injection surface? what does the shared FS
API look like? **If deepagents cannot cleanly drive our models, L2/L3 are blocked** —
we stop at L1 (still a valid result: "tracing yes, deepagents not feasible here") and
report. `deepagents` is added to `requirements.txt` only if a level ships.

## Skills used (already installed)

- `deep-agents-core` — build the deepagents agent (L3).
- `deep-agents-orchestration` — subagent spawn pattern (L3 per-author subagents).
- `deep-agents-memory` — shared filesystem / memory (L2 + L3 context channel).
- `langgraph-persistence` — checkpointer if state must survive across calls.
- `langchain-fundamentals` — model wiring.

Invoked during implementation to get the patterns right rather than guessing.
**Optional deliverable:** a small project skill `stage-harness-ablation` capturing the
eval-flow playbook (prepare → levels → compare → verdict) so organize/planner-chain
ablations are turnkey. Decided at implementation time; a markdown playbook is the
fallback.

## The comparison (reuses the eval methodology)

- **Frozen inputs:** for each fixed question, retrieve sources ONCE and freeze them
  (like the ts-components eval), so retrieval variance is excluded and every level sees
  identical sources.
- **Questions:** 3 fixed **fan-out** questions (broad/comparative, so the orchestrator
  runs ≥ 2 workers — e.g. "Compare frequentist and Bayesian estimation", "Contrast
  bias-variance tradeoff across regularization, model selection, and ensembles",
  "Compare OLS and MLE"). Narrow questions never trigger orchestrator-workers, so they
  are excluded here.
- **Per level, per question:** run the workflow; capture final answer, per-stage tokens,
  latency, USD; from L1+ capture the traced brief→synthesizer handoff.
- **Judge:** nano (fixed) + gold, 1–5 on **faithfulness**, **coverage**,
  **synthesis/comparison quality** (did it actually compare the authors, not just
  concatenate?), **coherence**.
- **Context-fidelity metric:** the headline number — did facts present in the worker
  briefs survive into the final answer? Scored by the nano judge comparing the briefs
  (captured from traces at L1+) against the final answer; at L0 the briefs are captured
  by instrumenting `_format_author_briefs`. This directly quantifies "context handling
  between models."
- **Artifact:** one markdown table (level × question) with quality dims +
  context-fidelity + USD/latency/tokens, plus an Opus verdict on **whether each level
  earns its complexity** and which level to keep.

## Controlled aspects (the "other aspects")

- **Cost:** capped `max_completion_tokens` + per-call `asyncio.wait_for` timeout; frozen
  sources (no repeated retrieval); spike-before-commit to avoid a deepagents runaway;
  LangSmith free tier; free-text parsing where models emit JSON (avoids the qwen
  `json_schema` hang and gemini trailing-comma failures already on record).
- **Rollback / safety:** every level behind `TUTOR_OW_HARNESS`, L0 default, automatic
  L0 fallback on any exception; prod `requirements.txt` untouched until a level wins;
  pilot built on its own branch.
- **Reproducibility:** frozen sources + fixed questions + fixed judge + temperature 0 +
  incremental persist (a mid-run crash loses nothing).
- **Feasibility gate:** the spike (Task 1) can halt L2/L3 before any pipeline change.

## Lockstep artifacts (if L1–L3 ship behind the flag)

| Artifact | Change |
|---|---|
| Backend | `agents/orchestrator_workers.py` (+ a small `agents/ow_harness.py` for the level dispatch) |
| Env flag | `TUTOR_OW_HARNESS` + env table in `docs/services/chat-features/36-deep-tutor.md` |
| Tracing | LangSmith init (env-gated) at the chat entry; no logic change |
| Per-feature doc | new `docs/services/chat-features/55-ow-harness-ablation.md` |
| Modal card | `web/src/data/tutorPipeline.ts` orchestrator node note (only if a non-L0 level becomes default — not in this pilot) |
| Eval | `src/services/chat/eval/ow_harness_compare.py` + artifact `docs/superpowers/eval/2026-06-04-ow-harness-ablation.md` |
| Tests | `tests/test_ow_harness.py` (level dispatch + L0 fallback) + eval pure-helper CI tests |
| Methodology | `docs/services/chat-features/eval-methodology.md` (the playbook) |
| Invariants + changelog | note the flag + the "harness levels fall back to L0" invariant |

## Testing

TDD. Unit-test the level dispatcher (flag 0→L0; unknown/failure→L0; 1/2/3 route to the
right path via monkeypatched level fns) and the eval pure helpers (render, judge parse,
context-fidelity scoring) in CI with no network. L2/L3 deepagents paths get a smoke test
behind a marker (needs the spike to pass first). Full chat suite + web tests stay green.

## Out of scope (YAGNI)

- No model sweep in this pilot — model held constant; the model×stage combination sweep
  is the *next* program phase, run only on the winning level.
- No conversion of organize or planner-chain yet — they are later pilots reusing this
  methodology.
- No default flip — L0 stays default; a winning level is proposed, not auto-shipped.
- No deepagents in prod deps until a level wins.

## Roadmap (sequential, after this pilot)

```
Pilot 1 (this)  orchestrator-workers harness ablation L0..L3 → keep winning level
Pilot 2         organize stage — same ablation, reuse methodology
Pilot 3         planner-chain — same ablation
Then            model×stage combination sweep on the winning levels → best combination
```
