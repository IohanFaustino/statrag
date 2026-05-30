# Deep-Tutor Efficiency — Phase 3: Adaptive Routing (light-touch)

**Date:** 2026-05-30
**Status:** Approved (design) — simple-tier behavior = light-touch (zero quality loss)
**Depends on:** Phase 1 (`b765aa8`), Phase 2 (`98140b5`)

## Background

Phase 2 upgraded the draft model and added a related-framings facet. Net win:
worst-case latency halved (156s→85s), tokens flat, quality up. The one cost:
**simple questions** now pay for additive work they don't need — the
synthesis-plan call (~5–15s) and the extra related-framings retrieval queries
(`parallel_extract_retrieve` rose to 7–23s). Simple-Q total went 38s→73s.

Phase 3 routes by complexity to claw that back **without losing quality**.

## Decision: light-touch tier (not speed-tier)

The draft model is the quality lever; it stays **full for every tier**. A
simple question only **skips the additive stages that don't help it**:
- the synthesis-plan call (a simple/single-concept answer needs no thesis +
  contrast scaffolding), and
- the related-framings extra retrieval queries (a narrow factual question has
  no other parents to surface).

Skipping these costs no quality on a genuinely simple question — they are
additive scaffolding for broad/comparative questions. Result: ~73s→~55s on
simple Qs, zero model downgrade, no floor reduction.

Rejected: routing simple Qs to nano draft (reintroduces the weaker
articulation + 134s-spike model we removed in Phase 2; risks thin answers and
misrouting). Available later behind a flag if more clawback is wanted.

## Goal

Use the planner's existing breadth signal to skip additive stages on simple
questions. No new LLM call, no model change, no new pipeline node.

## Scope — one change, one signal

### Complexity signal (reuse, no new call)

- **Source:** the query planner (`extract_concepts_ex` /
  `EXTRACT_CONCEPTS_BUDGET_PROMPT`) already returns `perspectives` ∈ 1–N
  ("1 = narrow/factual; 2 = standard; 3+ = broad/debated/comparative").
- **Tier rule:** `simple` ⇔ `perspectives <= 1`; otherwise `standard`.
  This reuses an already-emitted field — no schema/LLM change beyond reading it.

### Routing behavior

- **Artifact:** `src/services/chat/agents/deep_tutor.py` (`run_deep_tutor`):
  - When tier is `simple`:
    - **Skip synthesis-plan** — set the plan task to off (same effect as
      `stageModels["plan"]="off"` / `TUTOR_SYNTHESIS_PLAN=0`) for this request.
    - **Drop the related-framings queries** — use only the core
      facet queries, not the extra framing query, in the multi-query pull.
      (The planner still emits them; selection just doesn't fan out on them.)
  - When tier is `standard`: current Phase-2 behavior unchanged.
  - Full draft model in **both** tiers (no per-tier model).
- **Env:** `TUTOR_ADAPTIVE_ROUTING` (default `1`); `0` = always standard
  (Phase-2 behavior), the rollback.
- **Data flow:** tier computed once from the planner result before the
  plan/retrieval fan-out; pure-local branch.
- **Error handling:** if `perspectives` is missing/unparseable, default to
  `standard` (fail toward quality — never strips stages on doubt).

### Modal diagram (the graph users see)

- **Artifact:** `web/src/data/tutorPipeline.ts` + `web/src/components/PipelineDiagram.tsx`;
  backend mermaid in `docs/services/chat-features/36-deep-tutor.md`;
  reference `docs/common ground/index.html`.
- **Change:** NO new node. Annotate the existing **synthesis-plan** node /
  edge as conditional: "skipped when the planner rates the question simple
  (perspectives ≤ 1)". Mirror the wording in the backend mermaid graph.
- **Verification (REQUIRED):** after the change, open the tutor **(i)** modal on
  :5175 and confirm it visually matches `docs/common ground/index.html` — the
  modal has drifted before.

## Verification

1. `pytest src/services/chat/tests/test_deep_tutor.py` green (+ new routing tests).
2. New tests: (a) `perspectives=1` ⇒ plan skipped + framing queries dropped;
   (b) `perspectives>=2` ⇒ Phase-2 behavior intact; (c) missing `perspectives`
   ⇒ standard (fail-safe); (d) `TUTOR_ADAPTIVE_ROUTING=0` ⇒ always standard.
3. Re-measure the 4 baseline queries via SSE:
   - "Define variance" / "Overfitting" (simple) ⇒ total should drop toward
     ~55s; no synthesis-plan timing; fewer retrieval queries.
   - "Bias-variance" / "L1 vs L2" (standard) ⇒ unchanged from Phase 2 (~85s),
     framing breadth retained (ridge/ensemble/regularization still present).
4. Browser on :5175: simple answer still has all 6 aspects, decomposition, clean
   LaTeX; (i) modal matches the reference diagram.

## Interconnected artifacts (lockstep)

| Aspect | File |
|---|---|
| Backend logic | `agents/deep_tutor.py` (tier compute + plan/query gating) |
| Env flag | `TUTOR_ADAPTIVE_ROUTING`, doc 36 env table |
| Modal card | `web/src/data/tutorPipeline.ts`, `web/src/components/PipelineDiagram.tsx` |
| Backend mermaid graph | `docs/services/chat-features/36-deep-tutor.md` |
| Per-feature doc | `docs/services/chat-features/36-deep-tutor.md` (routing section), `45-query-planner-coverage.md` |
| Reference graph | `docs/common ground/index.html` (compare only; do not edit unless drifted) |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Tests | `tests/test_deep_tutor.py`, `web/src/components/PipelineDiagram.test.tsx` |

## Out of scope

- Speed-tier (nano draft for simple Qs) — only if a flag is later requested.
- GraphRAG-lite epic (separate; decided after measuring whether Phase-2
  framings already close the association gap — they appear to).

## Success criteria

- Tests pass; routing tests cover both tiers + fail-safe + rollback flag.
- Simple-Q latency drops (~73s→~55s); standard-Q unchanged + breadth retained.
- No quality loss on simple answers (6 aspects, decomposition, LaTeX intact).
- (i) modal matches the reference diagram on :5175.
