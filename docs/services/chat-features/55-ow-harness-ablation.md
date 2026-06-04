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
| L2 `2` | shipped (Plan B) | structured-JSON brief block (no deepagents) | `structured_briefs_block` |
| L3 `3` | eval experiment (Plan B) | deepagents synthesizer agent reads brief files | deepagents virtual FS (`ow_deepagents.py`) |
| L4 | deferred | full deepagents (subagent-per-author) | only if L3 wins (it didn't) |

L0 is default and the fallback; any level failure degrades to L0. L1 tracing never
changes outputs. L3 lazy-imports `deepagents` (not a prod dependency).

## Plan B A/B verdict (2026-06-04)

3-way A/B on scoped stats/econ sources, nano fixed, content-bearing fidelity:
**L2 ≈ L0** (structured handoff = no effect); **L3 deepagents = +0.41 quality but
−0.67 fidelity** (shorter answers, fewer brief facts retained) on a tiny 3-question /
1-run sample with unreliable L3 cost accounting. **Not shipped** — L0 stays default;
deepagents not added to deps. Program takeaway: the OW context-handling weakness is not
fixed by reformatting the handoff or a deepagents synth — it likely lives upstream
(retrieval / lossy worker summaries). See `2026-06-04-ow-harness-ablation.md`.

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

## Plan C — powered deepagents skills+subagents comparison (2026-06-04)

4 synthesizer arms (nano fixed), 6 questions × 3 runs = 72 runs, full-text judge, **real
token capture** (`UsageMetadataCallbackHandler`): L0 current synth · L3a bare deepagents ·
L3b deepagents + a written synthesis `SKILL.md` (`ow_skills/synthesis/`) · L4 deepagents +
subagents-per-author. Harness `eval/ow_deepagents_compare.py`; arms in `ow_deepagents.py`
(`synthesize_with_skill`, `synthesize_with_subagents`).

**Verdict (`docs/superpowers/eval/2026-06-04-ow-deepagents-compare.md`):** **L3b wins** —
beats L0 on all 6 questions (quality 4.39 vs 3.96, fidelity 4.50 vs 3.39) at ~$0.0046/answer;
the SKILL is the active ingredient (L3b ≫ L3a bare). **L4 subagents rejected** (worse than
L3b at 1.6× its cost, ~7× L0). L3b → adopt-candidate; productionizing (DeepTutorAnswer
schema + deepagents dep + latency gate) is Plan D. deepagents stays out of `requirements.txt`.

## Plan D — L3b shipped as opt-in (2026-06-04)

L3b productionized as **harness level 5 / `tutorWorkflow="orchestrator-deep"`** (Plan D).
`deepagents==0.6.8` added to `requirements.txt`. Free text from `synthesize_with_skill` is
mapped to a streamable `DeepTutorAnswer` via a nano schema-fill pass. Default behavior
unchanged; any L5 failure falls back to L0. See [doc 56](56-deep-synthesis-l3b.md) for the
full design and synced-artifacts checklist.
