# Plan C — Powered deepagents synthesizer comparison (skills + subagents)

**Date:** 2026-06-04
**Status:** approved (design)
**Builds on:** Plan B (`2026-06-04-ow-harness-planb-design.md`) + the corrected fidelity
metric (`_JUDGE_CHARS=12000`). Motivated by: the Plan B L3 tested only *bare* deepagents
(single agent, no skills, no subagents) and was underpowered (3q/1run) with understated
L3 cost. Plan C settles, properly, whether a deepagents harness with **skills** and
**subagents** beats the current synthesizer.

## Goal

Run a powered, honestly-costed comparison of four synthesizer arms over the
orchestrator-workers stage — current synthesizer vs three deepagents configurations of
increasing capability — and decide, with a spread-aware rule, whether any arm earns
adoption. Workers and model are held constant (nano) so the variable is purely the
synthesizer.

## Arms (synthesizer only; nano workers produce the AuthorBriefs for every arm)

| Arm | Synthesizer | deepagents features |
|---|---|---|
| **L0** | current code (`run_orchestrator_workers` level 0) | none (baseline) |
| **L3a** | `synthesize_with_deepagents` (Plan B) | bare agent + virtual-FS brief files |
| **L3b** | `synthesize_with_skill` (new) | + a written synthesis `SKILL.md` (SkillsMiddleware) |
| **L4** | `synthesize_with_subagents` (new) | + one subagent per author (SubAgentMiddleware), then integrate |

L2 (structured-JSON handoff) is dropped — Plan B showed it ≈ L0.

## Power & measurement

- **6 fan-out questions** (orchestrator-workers fires at ≥2 authors) × **3 runs/arm** =
  72 synthesizer runs. Frozen sources reused across arms+runs (retrieval excluded).
- **Per (arm, question): mean + spread** (min/max and stdev) across the 3 runs. A delta
  vs L0 only counts if it **exceeds the spread**.
- **Full-text judge** (`_JUDGE_CHARS=12000`) for quality (faithfulness/coverage/
  synthesis/coherence) + content-bearing fidelity; judge **each run, average**.
- **Real token capture:** a LangChain usage callback
  (`langchain_core.callbacks.UsageMetadataCallbackHandler` or
  `langchain_community.callbacks.get_openai_callback`) attached to `agent.invoke`
  captures **all** LLM turns — main agent, subagents, and tool-call reads — so L3a/L3b/L4
  USD is the true total (fixes Plan B's understated L3 cost). L0 captures `resp.usage`.

## The written synthesis skill (L3b)

A new `SKILL.md` (e.g. `src/services/chat/agents/ow_skills/synthesis/SKILL.md`) with
proper frontmatter (`name`, `description`) and instructions distilled from the existing
`SYNTHESIZER_ADDENDUM` / `DEEP_TUTOR_INSTRUCTIONS`: read every brief file, integrate into
one throughline, compare authors explicitly, retain each content-bearing key point,
ground every claim, no fabrication. Loaded via `create_deep_agent(skills=[<dir>],
backend=FilesystemBackend(virtual_mode=True))`. This is the "skills written by you" arm.

## L4 subagents-per-author

`create_deep_agent` with a named `author-analyst` subagent (`{"name","description",
"system_prompt","skills":[synthesis dir]}`) plus a main system prompt that instructs the
agent to `task(agent="author-analyst", instruction=…)` once per author brief file, then
integrate the returned analyses into the final comparative answer. Skills are passed to
the subagent explicitly (custom subagents don't inherit). `thread_id` set per run.

## New / changed artifacts

| Path | Responsibility |
|---|---|
| `src/services/chat/agents/ow_skills/synthesis/SKILL.md` | the synthesis skill (L3b/L4) |
| `src/services/chat/agents/ow_deepagents.py` | `synthesize_with_skill`, `synthesize_with_subagents`, a shared `_run_agent(...)` with usage callback returning `(text, total_tokens)` |
| `src/services/chat/eval/ow_deepagents_compare.py` | the powered 4-arm eval (freeze → run×3 → judge → average → bands → artifact) |
| `src/services/chat/tests/test_ow_deepagents_compare.py` | CI unit tests (pure helpers: arm registry, averaging, band, render) |
| `docs/superpowers/eval/2026-06-04-ow-deepagents-compare.md` | artifact + verdict |
| docs 55 + changelog | record Plan C + verdict |

deepagents stays a manual install (not in `requirements.txt`) unless an arm wins.

## Decision rule

An arm is adopted only if **mean(arm) − mean(L0) > pooled spread** on quality, with
fidelity not regressing, **consistently across questions**, and at an acceptable real
token cost. Otherwise: inconclusive → keep L0, document why. No default flip and no
`DeepTutorAnswer`-schema productionization in Plan C — those are a follow-up if an arm
wins.

## Controlled aspects

Model fixed at nano (arms + judge); frozen reused sources; per-call cap + timeout;
incremental persist (72 runs — a crash must lose nothing); deepagents lazy/gated;
background execution; judge full-text + averaged.

## Testing

TDD on pure helpers only (no network): arm registry/labels, the 3-run averaging + spread
computation, artifact rendering with bands, token-callback total extraction (feed a fake
usage object). The deepagents arms are smoke-tested behind `pytest.importorskip
("deepagents")`; the real 72-run comparison is the orchestrator live run. Full chat suite
+ web stay green.

## Out of scope (YAGNI)

- No production wiring of L3b/L4 into `run_orchestrator_workers` (Plan B already wired L3
  bare; skill/subagents arms live in `ow_deepagents.py` + the eval). Wire a winner later.
- No HITL / checkpointer-persistence features of deepagents (not needed for synthesis).
- No `requirements.txt` change unless an arm wins.
- No model sweep (nano fixed) — that is a separate later phase.
