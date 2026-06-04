# Chained Question-Decomposition Query Planner — Design

**Date:** 2026-06-04
**Status:** approved (design)

## Goal

Rework the deep-tutor **query planner** from a single nano call into a flag-gated
**3-step prompt chain** (decompose → expand → consolidate) that performs explicit
**question decomposition**, then run a 3-model comparison (nano / gemini / qwen-plus,
+ single-call baseline) to see which model drives the best plan.

The planner's output type and every downstream stage are unchanged; this is an
internal rework of how the `QueryPlan` is produced, plus an offline eval.

## Background — current planner

`extract_concepts_ex(query, *, model, max_authors) -> QueryPlan` in
`src/services/chat/agents/deep_tutor.py` makes ONE nano call against
`EXTRACT_CONCEPTS_BUDGET_PROMPT` (`prompts/deep_tutor.py`) and parses a single JSON
blob into `QueryPlan(concepts, suggested_authors, queries, facets)`. The prompt
mandates an application-case facet and a related-framings facet. On any failure it
degrades to the keyword heuristic (`extract_concepts`). Parsing is `json.loads(
strip_fences(...))` — no `response_format`.

## Architecture

`extract_concepts_ex` becomes a **dispatcher**:

```
_PLANNER_CHAIN_ON = os.environ.get("TUTOR_PLANNER_CHAIN", "0") == "1"

extract_concepts_ex(query, *, model, max_authors):
    if _PLANNER_CHAIN_ON:
        try:
            return await extract_concepts_chain(query, model=model, max_authors=max_authors)
        except Exception:
            logger.exception("planner chain failed; degrading to single-call planner")
            # fall through to the existing single-call body
    <existing single-call planner body>   # itself degrades to keyword heuristic
```

- Default (`TUTOR_PLANNER_CHAIN` unset/`0`) = today's behaviour, byte-for-byte.
- `=1` = the 3-step chain, with the single-call planner as automatic fallback on
  any chain exception.
- Output is always a `QueryPlan`; downstream code is untouched.

## The 3-step chain

`extract_concepts_chain(query, *, model, max_authors) -> QueryPlan`, all steps using
`model` (default nano), `temperature=0.0`, `max_completion_tokens≈300`, plain JSON
parsed with `strip_fences` (no `response_format` — also dodges the qwen `json_schema`
hang, see [[qwen-plus-json-schema-hang]]).

```
Q --[1 DECOMPOSE]--> {"sub_questions": [sq1..sqN]}
  --[2 EXPAND]-----> {"items": [{"sub_question","concept","query","facet"} ...]}
  --[3 CONSOLIDATE]-> {"concepts":[..≤3], "perspectives":1..max_authors,
                       "facets":[..≤6], "queries":[..≤5]}  ->  QueryPlan
```

**Step 1 — DECOMPOSE (`PLANNER_DECOMPOSE_PROMPT`).** Input: the user question.
Output: 2–5 atomic sub-questions that together cover what the answer must address.
The two guarantees that live in today's single prompt **move here**: the list MUST
include one application-case sub-question (a real/empirical use) and one
related-framings sub-question (other parent contexts). Narrow questions yield 2;
broad/comparative yield up to 5.

**Step 2 — EXPAND (`PLANNER_EXPAND_PROMPT`).** Input: original question + the
sub-question list. Output: one `item` per sub-question, each with a canonical
`concept` (short noun phrase), a self-contained retrieval `query` (textbook-phrased,
not an echo of the question), and a `facet` (the thing the answer must cover for that
sub-question). 1:1 mapping preserves decomposition.

**Step 3 — CONSOLIDATE (`PLANNER_CONSOLIDATE_PROMPT`).** Input: the expanded items +
`max_authors`. Output: the final plan — dedupe near-duplicate facets/queries, cap to
≤3 concepts / ≤6 facets / ≤5 queries, and judge `perspectives` (1 = narrow, up to
`max_authors` for broad/comparative) from the breadth of the sub-questions. Stays an
LLM call (it makes the same breadth judgement the single planner makes today), not
pure-Python dedupe.

Each step clamps its outputs with the same defensive list-comprehension parsing used
today (`[str(x).strip() for x in ... if str(x).strip()][:N]`). Empty/unparseable
output at any step raises → dispatcher falls back to single-call.

## Eval (part 2)

New module `src/services/chat/eval/planner_chain_compare.py`, reusing the
`ts_components_compare.py` harness shape: per-contestant disk persistence, hard
`max_completion_tokens` cap + `asyncio.wait_for` timeout, free-text + `strip_fences`
parsing (so qwen works), fixed nano judge, one markdown artifact, incremental writes.
**No Qdrant** — the planner does not retrieve.

- **Contestants:** `nano-chain`, `gemini-chain`, `qwen-chain` (each model runs all 3
  chain steps), plus `single-call (nano)` baseline (today's planner) to show whether
  chaining helped.
- **Questions (fixed 3):** narrow `"State the bias of an unbiased estimator."`;
  standard `"What are the components of a time series?"`; broad
  `"Compare L1 and L2 regularization."`.
- **Judge:** nano, 1–5 on **decomposition** (sub-questions atomic + complete),
  **coverage** (facets incl. application-case + related-framings), **targeting**
  (queries self-contained, ~one per facet, not echoing the question),
  **redundancy** (low duplication; 5 = none). Overall = mean.
- **Captured:** in/out tokens, USD (`usd_est`), ms — chain = 3 calls, so cost ≈ 3×
  the single call; the table makes that visible.
- **Artifact:** `docs/superpowers/eval/2026-06-04-planner-chain-model-compare.md`
  (per-(contestant×question) scores + plan dumps + my verdict).

## Lockstep artifacts (CLAUDE.md interconnected-artifact rule)

| Artifact | Change |
|---|---|
| Backend logic | `agents/deep_tutor.py` — `extract_concepts_chain`, dispatcher, `_PLANNER_CHAIN_ON` |
| Prompts | `prompts/deep_tutor.py` — `PLANNER_DECOMPOSE_PROMPT`, `PLANNER_EXPAND_PROMPT`, `PLANNER_CONSOLIDATE_PROMPT` |
| Env flag | `TUTOR_PLANNER_CHAIN` + env table in `docs/services/chat-features/36-deep-tutor.md` |
| Modal card | `web/src/data/tutorPipeline.ts` planner node label/description → "decompose → expand → consolidate"; `PipelineDiagram.tsx` only if a structural node change is needed |
| Backend mermaid | `docs/services/chat-features/45-query-planner-coverage.md` graph (+ doc 36 if it shows the planner) |
| Per-feature doc | new `docs/services/chat-features/54-planner-chain.md` |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Tests | backend `tests/test_*` (parsers + dispatcher + fallback); `web/src/components/PipelineDiagram.test.tsx` if the node changed |

After the diagram/stage change: open the tutor (i) modal on :5175 and confirm it
matches `docs/common ground/Elements/index.html`.

## Testing

TDD. Backend unit tests (no network — feed canned JSON strings to the parsers):
- each step parses well-formed JSON, fenced JSON, and clamps to caps;
- malformed/empty step output raises;
- dispatcher: flag on → chain path; chain raises → single-call path; flag off →
  single-call path (assert via monkeypatched step stubs / the flag).
Eval pure helpers (artifact render, judge parse) unit-tested in CI; the live run is
manual via `python -m`. Full chat suite + web tests must stay green.

## Out of scope (YAGNI)

- No change to the QueryPlan type, downstream retrieval, or coverage stage.
- No `response_format`/structured-output on the planner (keeps qwen working).
- No new default — the chain stays behind the flag until the eval justifies a flip.
- Eval judges the PLAN only, not end-to-end retrieval/answer quality.
