# 45 — Query planner (top orchestrator) + coverage check

## Why

"What is the bias-variance tradeoff?" used to retrieve on the **raw question
only** and the draft gave the bias formula but not the variance formula. Two
causes: retrieval coverage (the variance-formula chunk never entered the pool)
and synthesis asymmetry. Option 2 fixes both with a top orchestrator that plans
retrieval + a coverage check that verifies it.

## Flow

```
Question
  → Query planner (nano, extract_concepts_ex → QueryPlan)
       concepts + suggested_authors + queries[] + facets[]
  → raw-query wide pull ‖ multi-query (one hybrid_search per query) → RRF merge
  → density select + author diversity + rerank → sources
  → Coverage check: assess_coverage(facets, sources) → missing
       missing → fill_missing_facets (re-query, cap 1) → re-rank
  → Planner → draft (single, + "give each named component its formula")
  → Answer
```

The **raw question is always retrieved** (anchor); multi-query only adds and
RRF-fuses. The coverage check is the self-healer: the planner declares the
`facets` the answer needs, and the system verifies they were actually retrieved.

## Config

| Knob | Where | Default | Meaning |
|---|---|---|---|
| `TUTOR_MULTI_QUERY` | env | `1` | `0` = raw-query retrieval only |
| `TUTOR_COVERAGE_CHECK` | env | `1` | `0` = skip coverage + re-query |

Both off ⇒ exactly the legacy single-query path.

## Code

- `agents/deep_tutor.py` — `QueryPlan`, `extract_concepts_ex` (now returns it),
  `_rrf_merge`, `_multi_query_candidates`; coverage wiring in `run_deep_tutor`.
- `agents/coverage.py` — `assess_coverage`, `fill_missing_facets`.
- `prompts/deep_tutor.py` — `EXTRACT_CONCEPTS_BUDGET_PROMPT` (queries+facets),
  `COVERAGE_PROMPT`, `formal_statement` symmetric-coverage nudge.
- Frontend — `tutorPipeline.ts` (Query planner relabel + Coverage node),
  `PipelineDiagram.tsx`.

## Tests

`src/services/chat/tests/test_query_planner_coverage.py` — RRF merge dedup/order,
planner graceful fallback, coverage graceful + facet-scoped, re-query dedup.

## Related-framings facet (Phase 2, 2026-05-30)

`EXTRACT_CONCEPTS_BUDGET_PROMPT` was extended to always include a
**related-framings facet** — the other contexts or parent theories the concept
belongs to beyond the most obvious framing. For "bias-variance tradeoff" this
surfaces "other contexts where the bias-variance tradeoff arises (e.g.
regularization, model selection, ensemble methods)" plus a matching retrieval
query.

- No new LLM call: enriches the existing single planner output.
- The extra query flows into the existing multi-query RRF pull, so retrieval
  coverage widens to alternative framings without extra latency overhead.
- The bias-variance example in the prompt is updated to show both facets.

## Adaptive routing and the related-framings query (Phase 3, 2026-05-30)

`run_deep_tutor` reads `perspectives` from the planner's `QueryPlan` to
compute a complexity tier (`simple` ⇔ `perspectives <= 1`). For `simple` tier
and `TUTOR_ADAPTIVE_ROUTING=1` (default):

- The **related-framings query** (last entry in `queries`, per prompt structure)
  is dropped from the multi-query fan-out. A narrow/factual question has no
  meaningful alternative framings to surface.
- The **synthesis-plan** stage is skipped (see doc 36).

The planner still emits the related-framings query in its output; Phase-2
prompt behavior is unchanged. Only the retrieval fan-out selection changes.
See doc 36 Phase 3 section and the spec at
`docs/superpowers/specs/2026-05-30-tutor-phase3-adaptive-routing-design.md`.

## Notes

- Best-effort throughout (invariant #19): any LLM failure degrades to the
  legacy path; coverage re-query capped at 1.
- The per-author orchestrator-workers drafting mode is unchanged (optional).
- Possible follow-up: spell the variance formula fully (the coverage check
  surfaces the facet; a stronger `formal_statement` example would expand it).
