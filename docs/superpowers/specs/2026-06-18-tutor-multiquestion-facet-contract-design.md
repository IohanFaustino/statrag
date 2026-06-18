# Tutor — multi-question facet contract (Scope A)

**Date:** 2026-06-18
**Status:** approved (brainstorming gate)
**Scope:** A only (core, true-by-construction). B (decompose-chain hardening), C (narrative thread/spine), D (coverage retry-and-enforce) are follow-ups, out of scope.

## Problem

Multi-question prompts answer poorly. Example:
> "What is stationarity? What are its versions? What is a unit root?"

Should become three distinct asks woven into one narrative, each with verbatim formal definitions (strict + weak/covariance stationarity, unit root). Today it doesn't, because:

- The robust decompose chain is off by default (`TUTOR_PLANNER_CHAIN=0`); the default single-call planner collapses "versions" into one bundled facet, so strict vs weak never become separate facets.
- Nothing forces "one question → ≥1 facet."
- Definition-form forcing (`_expand_concept`, `definition_gaps.py`) is a side-channel gated by `TUTOR_DEEP_DEFINITIONS` + `_query_is_definitional`, not bound to the planner's facet list. Its map (`_EXPAND`) covers stationarity→strict/weak/covariance but **has no `unit root`**, and `_DEFINITIONAL_RE` doesn't match "unit root".

## Decisions

- Scope **A** only.
- **Default ON** for multi-form definitional questions: the pure-code pieces always run; definition recovery auto-fires when injected definitional facets exist (no env flag required for these).
- Expansion map: minimal curated addition — add `unit root`; keep stationarity forms. Grow later as the corpus needs.

## Design

Principle: the **facet set is the one authoritative contract**. LLM proposes concepts/queries (cheap to be wrong); pure code guarantees every ask + every required definitional form survives into the facet set and into recovery (expensive to be wrong).

Data flow (new pieces in **bold**):
```
raw prompt
  → [code] multi_question_split → N asks         (split on sentence-final ?)
  → existing planner (1 call) → concepts, queries, base facets
  → [code] canonical facets := dedup( one-facet-per-ask ∪ base facets
                                      ∪ inject_definitional_forms(concepts ∪ asks) )
  → retrieval (unchanged)
  → [code] definition recovery fed the DEFINITIONAL facets   (bound, not side-channel;
        auto-fires when injected definitional facets exist)
  → draft / finalize / coverage receive the same facet set
```

Three units, each testable without an LLM:

1. `multi_question_split(prompt) -> list[str]` — pure regex. Split on sentence-final `?`. Guards: cap N (e.g. ≤5), ignore non-sentence-final `?`, single-question prompts return `[prompt]`.
2. `inject_definitional_forms(terms) -> list[str]` — promote the existing `_EXPAND` map out of the recovery side-channel; add `"unit root"` to `_EXPAND` and to `_DEFINITIONAL_RE`. Returns extra facet strings for any term with known forms.
3. **Binding** — `_recover_definitions_block` (deep_tutor.py) is fed the post-injection definitional facets (today: `concepts` only) and auto-fires when any exist, bypassing the `TUTOR_DEEP_DEFINITIONS`-only gate for these.

## Enforcement ladder

schema (facet set = contract) → code (split + injection + binding) → **test** (regression below) → prompt (untouched in A).

## Test (must fail on today's code)

`"What is stationarity? What are its versions? What is a unit root?"`:
- canonical facets ⊇ {strict stationarity, weak stationarity, unit root}
- definition recovery returns verbatim defs for all three.

Plus unit checks: `multi_question_split` (3 `?` → 3, internal `?` not over-split, single → 1); `inject_definitional_forms("unit root")` non-empty.

## Failure modes / cut list

- Over-split → sentence-final `?` only + cap.
- Injection over-firing → only inject for terms in the curated map.
- Cost → recovery already parallel; injection/split are free.
- **Cut (YAGNI):** no concept ontology, no new classifier LLM call, no general taxonomy — curated map + regex split only.
