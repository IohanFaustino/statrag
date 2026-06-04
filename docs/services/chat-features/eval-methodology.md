# Eval-flow methodology — prepare → compare → verdict

Reusable recipe for comparing models/harness-levels on a single pipeline stage.

## 1. Prepare (freeze inputs)
- Pick a small FIXED question set sized to the stage (e.g. fan-out questions for
  orchestrator-workers, which only fires at ≥2 authors).
- Retrieve sources ONCE per question and freeze them to disk. Every contestant
  sees identical inputs → differences are the variable under test, not retrieval.

## 2. Compare (run contestants)
- One contestant = one (model | harness-level). Hold all other axes constant so
  the result is interpretable (isolate one variable).
- Hard `max_completion_tokens` cap + per-call `asyncio.wait_for` timeout. Persist
  each result immediately (a crash loses nothing).
- Parse model output as FREE TEXT + `strip_fences` where possible: avoids the
  qwen `json_schema` hang and gemini trailing-comma failures (both on record).
- try/except per contestant → record FAILED, never crash the sweep.

## 3. Judge + verdict
- Fixed judge model (nano) + a gold anchor; score 1–5 on stage-specific dims.
- Capture USD (`usd_est` from real `resp.usage`), latency, tokens.
- Emit ONE markdown artifact: score table + raw outputs + a human (Opus) verdict
  that calls out judge artifacts (e.g. uniform conciseness scores carry no signal)
  and whether the added cost/complexity earns its place.

## Known model quirks (design around them)
- qwen-plus: hangs under `response_format=json_schema` → free-text + parse.
- gemini-2.5-flash: emits non-strict JSON (trailing commas) → free-text + lenient parse.
- nano (reasoning): needs generous token budgets or it truncates JSON mid-string.

## Examples in repo
- `src/services/chat/eval/ts_components_compare.py`
- `src/services/chat/eval/planner_chain_compare.py`
- `src/services/chat/eval/ow_harness_compare.py`
