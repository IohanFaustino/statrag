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
- Definition-form forcing (`_expand_concept`, `definition_gaps.py`) is fed the planner's `concepts`, not the per-question subjects. `TUTOR_DEEP_DEFINITIONS` already defaults ON and `_query_is_definitional` already matches "what is/are", so the machinery runs — but a multi-question prompt's later subjects (unit root, the versions) never reach the detector. Its map (`_GENERIC_EXPANSIONS`) expands stationarity→strict/weak/covariance; **unit root needs no map entry** (no sub-forms — it passes through as itself once it reaches the detector). The `_MAX_GAPS=3` cap also truncates the 4 required forms (strict/weak/covariance + unit root).

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
2. `concepts_from_asks(asks) -> list[str]` — pure regex; strips question scaffolding/articles to get each ask's bare subject ("stationarity", "unit root"). No map/regex changes needed; raise `_MAX_GAPS` 3→5 so 4 forms aren't truncated.
3. **Binding** — at the single site where `concepts`/`facets` are read from the plan (`deep_tutor.py:2822`), union ask-subjects into `concepts` (FIRST, to survive the cap) and the asks into `facets`. Definition recovery (already default-on) then sees every question's subject.

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
