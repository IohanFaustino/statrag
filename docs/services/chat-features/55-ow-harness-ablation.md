# 55 — Orchestrator-workers harness ablation

## Why

The orchestrator-workers stage (doc 44) hands worker `AuthorBrief`s to the synthesizer
as a **flattened string** (`_format_author_briefs`). This pilot tests whether a
harness improves that inter-model context handoff and the answer quality — by running
the *same* stage across increasing harness levels, model held constant (nano), so the
measured delta is the harness, not the model. First pilot of a sequential program
(organize and planner-chain follow). See the eval-flow playbook:
`docs/services/chat-features/eval-methodology.md`.

## Harness levels — `TUTOR_OW_HARNESS`

| Level | Status | Added capability | Brief→synthesizer channel |
|---|---|---|---|
| L0 `0` | shipped (default) | none | `_format_author_briefs` → flat string |
| L1 `1` | shipped | LangSmith tracing (behavior identical) | same string, now traced |
| L2 `2` | **Plan B** | deepagents shared virtual filesystem | per-author brief *files* |
| L3 `3` | **Plan B** | deepagents planning + subagent-per-author + memory | deepagents end-to-end |

L0 is default and the fallback; any harness failure degrades to L0. L1 tracing never
changes outputs. In Plan A, levels 2/3 parse through the flag but only enable tracing
(no deepagents code yet); they ship in Plan B.

## Plan A artifacts (this doc)

- `src/services/chat/agents/ow_harness.py` — `ow_harness_level()` (flag parse, safe
  default) + `maybe_traced(fn, name=…)` (LangSmith `@traceable` passthrough; no-op at
  L0 or without `LANGSMITH_API_KEY`; never changes behavior).
- `src/services/chat/agents/orchestrator_workers.py` — `on_briefs` capture hook (fires
  with the worker briefs before synthesis; best-effort) + worker call wrapped in
  `maybe_traced`.
- `src/services/chat/eval/ow_harness_compare.py` — freeze multi-author sources → run L0
  → judge quality (faithfulness/coverage/synthesis/coherence) + **context-fidelity**
  (did brief facts survive synthesis). Artifact:
  `docs/superpowers/eval/2026-06-04-ow-harness-ablation.md`.
- Spike: `docs/superpowers/eval/_spike/deepagents-findings.md` — **deepagents FEASIBLE**
  (drives nano via `ChatOpenAI`; virtual filesystem works).

## Baseline finding (L0)

Quality mediocre (overall 2.5–3.25), faithfulness + context-fidelity low. Caveat: the
baseline is partly confounded — all-book `top_k=10` retrieval pulled off-topic authors
whose "no-info" briefs were (correctly) dropped, depressing fidelity. **Plan B first
scopes retrieval to relevant books and refines the fidelity metric to content-bearing
briefs, re-baselines L0, then builds and A/B-tests L2.** See the artifact's verdict.

## Plan B (next)

deepagents L2 (synthesizer reads brief files from the virtual FS) then, if it wins, L3
(subagent-per-author). Flag-gated, L0 fallback, model fixed at nano. API + path in the
spike findings doc.
