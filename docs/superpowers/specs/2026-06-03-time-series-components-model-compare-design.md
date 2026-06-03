# Time-Series-Components Model Comparison — Design

**Date:** 2026-06-03
**Status:** approved (design)

## Goal

Produce one artifact comparing how five contestants answer a single fixed
question — *"What are the components of a time series?"* — when every contestant
is handed the **same frozen RAG context** retrieved from the project's own RAG
system. Measure answer quality (LLM-judged vs a gold anchor), cost (USD), latency,
and token usage; close with a human (Opus) qualitative verdict.

This is an offline, manually-run eval. It does **not** modify the shipped chat
pipeline. It lives in `scripts/` + `docs/superpowers/eval/`.

## Contestants (5)

| Contestant | Path | Reasoning |
|---|---|---|
| `gpt-5.4-nano-2026-03-17` | API via `aclient_for` / router | prompt scratchpad |
| `gemini-2.5-flash` | API via router | prompt scratchpad |
| `qwen-plus` | API via router | prompt scratchpad |
| Claude Sonnet | delegated `Agent` subagent | native + prompt scratchpad |
| Claude Opus | delegated `Agent` subagent | native + prompt scratchpad |

All five receive an **identical** answer prompt and the **identical** frozen RAG
context. The prompt asks for a hidden `reasoning` scratchpad plus the judged
`answer`; the scratchpad is discarded, only `answer` is judged. This makes
"reasoning" uniform across contestants (none of nano/gemini/qwen has a wired
provider thinking toggle; only the prompt-scratchpad is model-agnostic).

## Pipeline — 4 steps, each persists to disk (resumable, token-burn-proof)

```
STEP 1  retrieve + freeze   (python, runs ONCE)
  sources, _ = hybrid_search(
      "What are the components of a time series? trend seasonality cyclical",
      book_slugs=["cerqueira", "spark_ts", "pesaran"],
      top_k=8, rerank=False)        # rerank=False so top_k is honored
  -> docs/superpowers/eval/_work/context.md   (frozen "RAG data", identical for all)

STEP 2  API trio            (python)
  for m in [nano, gemini, qwen-plus]:
    answer, in_tok, out_tok, ms = call_answer(m, context)   # capped + timeout
    -> docs/superpowers/eval/_work/answers/<m>.json  {answer, in_tok, out_tok, ms, ok}

STEP 3  Claude agents       (me, the orchestrator — not the script)
  dispatch Agent(model=sonnet) and Agent(model=opus); each:
    - reads _work/context.md and the shared answer prompt
    - produces an answer obeying the SAME ~250-400 word limit
    - writes _work/answers/sonnet.json and _work/answers/opus.json  (same shape)

STEP 4  judge + artifact    (python --step judge)
  gold = "trend, seasonal, cyclical, irregular/noise" (classical decomposition)
  for every _work/answers/*.json:
    scores = nano_judge(answer, gold, context)   # {clarity, faithfulness,
                                                  #  coverage, conciseness} 1-5
  -> docs/superpowers/eval/2026-06-03-time-series-components-model-compare.md
     (score table + USD/latency/tokens + full answers + gold reference)
  then I append an Opus prose verdict to that artifact.
```

## The answer prompt (shared, all contestants)

```
<role>You answer one statistics question for a learner, using ONLY the provided
context.</role>
<task>Answer: "What are the components of a time series?"</task>
<output_format>
Return ONLY a JSON object:
  "reasoning": 2-4 private sentences planning the answer (DISCARDED, never shown).
  "answer": a clear ~250-400 word explanation grounded in the context. Name and
      briefly explain each component. Use $...$ for any math. English only.
</output_format>
<rules>
Ground every claim in the context. If the context omits a classical component,
you may name it but say the context does not cover it. No invented citations.
</rules>

CONTEXT:
<frozen context.md>
```

The Claude agents (Step 3) get the same prompt text; because they reason
natively they may leave `reasoning` terse — only `answer` is judged, so this is
fair.

## The judge

Fixed model `gpt-5.4-nano-2026-03-17`. Scores each answer 1–5 on:

- **clarity** — is it understandable?
- **faithfulness** — claims grounded in context / no fabrication?
- **coverage** — how many of the gold components (trend, seasonal, cyclical,
  irregular) are correctly named & explained?
- **conciseness** — tight vs padded?

Overall = mean of the four. Judge prompt returns strict JSON; an unparseable
judge reply scores 0 on all dims (recorded, not crashed).

## Robustness — the prior token burn was qwen-plus runaway (67k out-tok / 85s)

1. **Retrieval runs once**, frozen to `context.md`; never re-run per contestant.
2. **Hard cap + timeout on every API call**: `max_completion_tokens=700` and
   `asyncio.wait_for(call, timeout=60)`. This directly kills the qwen runaway.
3. **try/except per call** — a failure writes `{"ok": false, "err": ...}` and the
   sweep continues; the artifact shows `FAILED` for that cell.
4. **Incremental persist** — `context.md`, each `answers/*.json`, and the final
   artifact are written as they complete. A mid-run crash loses nothing; rerun
   resumes from existing files.
5. **Agents bounded** — one dispatch each, read/write only, no retrieval (they
   consume the frozen context), short prompt.

## Files

| Path | Role |
|---|---|
| `scripts/ts_components_compare.py` | steps 1, 2, 4; `--step retrieve\|api\|judge` |
| `docs/superpowers/eval/_work/context.md` | frozen RAG context (intermediate) |
| `docs/superpowers/eval/_work/answers/*.json` | per-contestant answers (intermediate) |
| `docs/superpowers/eval/2026-06-03-time-series-components-model-compare.md` | **the one artifact** |

## Reuse (no new infra)

- `hybrid_search` (`src/services/chat/retrieval.py`) — retrieval.
- `aclient_for` + `apply_structured_output` (`src/services/chat/llm/`) — API calls,
  same pattern as `_chat_usage` in `facilitate_reasoning_eval.py` (returns usage).
- `usd_est` (`src/services/chat/cost.py`) — cost; prices already include
  nano/gemini/qwen.
- `Agent` tool — Sonnet/Opus contestants.

## Out of scope (YAGNI)

- No multi-question dataset — one fixed subject.
- No provider thinking-toggle wiring — prompt scratchpad only.
- No changes to shipped pipeline, schemas, or frontend.
- No new pytest marker integration unless trivially free; this is a script.
