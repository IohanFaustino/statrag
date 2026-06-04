# Orchestrator-Workers Harness Ablation — Plan B Design (L2/L3 + re-baseline)

**Date:** 2026-06-04
**Status:** approved (design)
**Builds on:** `2026-06-04-orchestrator-workers-harness-ablation-design.md` (parent spec)
and the Plan A baseline + verdict (`docs/superpowers/eval/2026-06-04-ow-harness-ablation.md`).

## Goal

Re-baseline the orchestrator-workers ablation on scoped sources + a fixed fidelity
metric, then add and A/B-test two new harness levels so any quality gain is cleanly
attributable: a **structured handoff (no deepagents)** and a **deepagents synthesizer
agent**. Model held constant at nano throughout. The deepagents level is an eval
experiment, not yet production-shipped.

## Level renumbering (`TUTOR_OW_HARNESS`)

| Level | Status after Plan B | What |
|---|---|---|
| 0 | shipped (default) | baseline — `_format_author_briefs` flat string |
| 1 | shipped | LangSmith tracing (observability-only) |
| 2 | **Plan B (production-wired)** | **structured handoff** — briefs as a JSON block to the same synthesizer; NO deepagents |
| 3 | **Plan B (eval experiment)** | **deepagents synthesizer agent** reads per-author brief files from a virtual filesystem |
| 4 | deferred | full deepagents (subagent-per-author) — only if L3 wins |

The A/B reads: **L2 − L0 = structure effect**; **L3 − L2 = deepagents-agent effect**.
`_MAX_IMPLEMENTED_LEVEL` rises to 3 (4 stays out-of-range → 0 until built).

## Eval fixes (do first — re-baseline)

1. **Scope sources.** `ow_harness_compare.BOOKS` becomes a fixed list of relevant
   stats/econ slugs: `["hansen", "wooldridge", "stock_watson", "gujarati", "baltagi",
   "pesaran", "islp", "murphy"]`. Workers then fan out over authors who actually treat
   the questions, not RAG/DL-ops texts. Re-freeze sources.
2. **Content-bearing fidelity.** A brief is "no-info" when its `summary` matches
   `not discuss|does not|no mention|not address` (case-insensitive) or it has empty
   `key_points`. The fidelity judge receives only content-bearing briefs; if fewer than
   2 remain, fidelity is recorded as `N/A` (not 0) and excluded from averages.
3. **Re-run L0** on the scoped frozen sources → trustworthy baseline the new levels must
   beat.

## Level 2 — structured handoff (production-wired)

In `run_orchestrator_workers`, gate on `ow_harness_level()`: at level ≥ 2 (but not the
deepagents path), replace the `_format_author_briefs(briefs)` flat string in the
synthesizer user message with a **structured JSON block**:

```
<author_briefs_json>
[{"author": "...", "summary": "...", "key_points": ["..."], "source_ranks": [..]}, ...]
</author_briefs_json>
```

Same synthesizer, same `DeepTutorAnswer` schema — only the brief representation changes.
Flag-gated, L0 fallback on any error, behavior-identical to L0 except the brief block.
Shippable. The level-2 vs level-3 split inside the workflow: level 2 = structured-JSON +
our synthesizer; level 3 = route synthesis to the deepagents module (below).

## Level 3 — deepagents synthesizer (eval experiment)

New `src/services/chat/agents/ow_deepagents.py`:

- Input: the user question, the source bundle, and the worker `AuthorBrief`s (still
  produced by our nano `run_author_worker`).
- Preload each brief as a file `briefs/<author>.md` (summary + key_points) via
  `deepagents.backends` `create_file_data` into a `FilesystemBackend(virtual_mode=True)`
  (or `StoreBackend` + `InMemoryStore`).
- Build `create_deep_agent(model=ChatOpenAI("gpt-5.4-nano-2026-03-17", api_key=...),
  tools=[], system_prompt=<synthesizer instructions: read every briefs/*.md file and
  synthesize, comparing authors explicitly>, backend=...)`.
- `agent.invoke({"messages":[{"role":"user","content":question}]},
  config={"configurable":{"thread_id": ...}})`; return the final message **text**.
- **Lazy import**: `import deepagents` inside the function; on `ImportError` raise a
  clear `RuntimeError("pip install deepagents to run harness level 3")`. deepagents is
  **NOT** added to `requirements.txt` in Plan B (per parent spec — only on a win).
- L3 output is free-text (no `DeepTutorAnswer` schema); the eval judges the text. Schema
  integration is deferred to a productionization plan if L3 wins.

The workflow dispatch (`run_orchestrator_workers` at level 3) returns a `DeepTutorAnswer`
with the deepagents text placed in the primary field so existing callers don't break;
but in Plan B only the **eval** exercises level 3 (production default stays 0).

## Eval — 3-way A/B

`ow_harness_compare.py` gains a `--level {0,2,3}` (or runs all three) producing rows
`L0 / L2 / L3` per question over the same scoped frozen sources. Same nano judge
(faithfulness/coverage/synthesis/coherence) + content-bearing fidelity. Capture
USD/latency/tokens (L3's deepagents loop will cost more — surfaced). One artifact
appends to / supersedes the Plan A baseline artifact; Opus verdict separates the
structure effect (L2−L0) from the deepagents-agent effect (L3−L2) and recommends keep /
drop / productionize.

## Controlled aspects

Model fixed at nano (all levels + judge); frozen scoped sources; per-call cap +
timeout; per-level flag + L0 fallback; deepagents lazy-imported, gated, and absent from
prod deps until a win; incremental persist; temperature 0.

## Lockstep artifacts

| Artifact | Change |
|---|---|
| Backend | `orchestrator_workers.py` (level-2 structured block + level-3 dispatch), new `agents/ow_deepagents.py`, `ow_harness.py` (`_MAX_IMPLEMENTED_LEVEL=3`) |
| Eval | `eval/ow_harness_compare.py` (scope, fidelity fix, L2/L3 rows) |
| Env flag | doc 36 `TUTOR_OW_HARNESS` row updated (2 structured, 3 deepagents) |
| Per-feature doc | `docs/services/chat-features/55-ow-harness-ablation.md` updated |
| Artifact | `docs/superpowers/eval/2026-06-04-ow-harness-ablation.md` (re-baseline + A/B) |
| Tests | `tests/test_ow_harness.py` (structured-block formatting, level dispatch, fidelity content-bearing filter; deepagents path behind a skip-if-not-installed marker) |
| Changelog | Plan B entry |

## Testing

TDD. Unit (no network): structured-JSON brief formatter; `_MAX_IMPLEMENTED_LEVEL`
clamp at 3; content-bearing brief filter; eval render with L0/L2/L3 rows. The deepagents
synthesizer gets a smoke test guarded by `pytest.importorskip("deepagents")`. Full chat
suite + web tests stay green. Live A/B run is orchestrator-run (needs deepagents
installed + Qdrant + keys).

## Out of scope (YAGNI)

- Level 4 (full deepagents subagent-per-author) — only if L3 wins.
- Production `DeepTutorAnswer`-schema integration for the deepagents synthesizer — only
  if L3 wins (then its own plan).
- No default flip; L0 stays default.
- deepagents not added to `requirements.txt` in Plan B.
