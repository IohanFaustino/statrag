# Plan — Qwen provider + multi-provider draft-model "battle"

**Date:** 2026-05-30
**For:** next session (no implementation done yet this session)
**Branch:** `feat/genai-ingest-deepseek` (current) — or cut `feat/draft-model-battle`
**Owner context:** assumes ZERO prior context. Read this top to bottom.

---

## 0 · Why this exists

The tutor draft-model A/B series found `gpt-5.4-2026-03-05` (full) is the most
*consistent* draft, and it is the current default (set via `TUTOR_DRAFT_MODEL`,
commit `98140b5`). **Problem: gpt-5.4 full is expensive — $2.50 in / $15.00 out
per 1M tokens.** A tutor draft is output-heavy (~35 input + ~2800 output tokens),
so output price dominates → **~$0.042 per answer**.

Goal of next session: find a **cheaper draft model that holds gpt-5.4-level
quality + consistency**, via a fair multi-provider battle. Cost is now a
first-class criterion alongside consistency/latency/LaTeX/quality.

### Estimated cost per answer (35 in + 2800 out tokens)

| Model | $/1M in | $/1M out | **$/answer** | notes |
|---|---|---|---|---|
| gpt-5.4 full (incumbent) | 2.50 | 15.00 | **~0.0421** | consistent, expensive |
| qwen-max (→3.7-max) | 2.50 | 7.50 | ~0.0210 | reasoning model (risk) |
| deepseek-v4-pro | 1.74 | 3.48 | ~0.0098 | reasoning; earlier rejected — RE-TEST w/ thinking disabled |
| gemini-2.5-flash | ~0.30 | ~2.50 | ~0.0070 | inconsistent depth (measured) |
| qwen-plus (→3.6-plus) | 0.325 | 1.95 | **~0.0055** | standard, 1M ctx — prime contender |
| groq gpt-oss-120b / llama-3.3-70b | ~0.15–0.60 | ~0.60–0.80 | ~0.001–0.002 | cheapest; quality unknown for draft |

Numbers are planning estimates — **verify live pricing** in-session (rates move).
`qwen-plus` is ~7.7× cheaper than gpt-5.4 on the dominant output cost; groq is
~20–40× cheaper. The battle decides whether any hold quality.

---

## 1 · Current state (what is already done)

- Providers IMPLEMENTED + tested: OpenAI, DeepSeek, Groq, **Gemini** (commit
  `34e7063`). Each is a `BaseLLM` subclass using the OpenAI SDK + a custom
  `base_url`. Routing in `src/services/chat/llm/router.py` via `get_llm` AND
  `aclient_for` (the tutor stages use `aclient_for`).
- Qwen is **NOT implemented** — only the design spec exists:
  `docs/superpowers/specs/2026-05-30-qwen-provider-draft-ab-design.md`.
- Keys already in `.env` (gitignored): `GEMINI_API_KEY`, `QWEN_API_KEY`
  (DashScope `sk-...`, len 116). **`tmp` file still holds both keys and is NOT
  gitignored — delete it once keys are confirmed in `.env`; never commit it.**
- Prior A/B verdicts (in memory `deepseek-model-unreachable.md`):
  - `deepseek-v4-pro`: rejected — ~9× latency, empty on hard query, broken
    LaTeX. **CAVEAT: may be because the draft path did not disable thinking.**
    Re-test with thinking disabled (see Task 2).
  - `gemini-2.5-flash`: works but depth inconsistent (600↔2864 tokens across
    identical runs). Kept as picker option only.

---

## 2 · Tasks

### Task 1 — Implement the Qwen provider (mechanical; clone Gemini)

Follow `docs/superpowers/specs/2026-05-30-qwen-provider-draft-ab-design.md`
exactly. This is a near-identical clone of the Gemini provider.

**Dispatch a sonnet subagent** with this work (TDD, no commit; orchestrator
verifies + commits):

1.1 **Config** (`src/core/config.py`): add
  `qwen_api_key: str = Field("", alias="QWEN_API_KEY")` and
  `qwen_base_url: str = Field("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", alias="QWEN_BASE_URL")`.
  Match the `gemini_api_key`/`gemini_base_url` style.

1.2 **Client** (new `src/services/chat/llm/qwen_client.py`): `QwenChat(BaseLLM)`
  — clone `gemini_client.py`, swap names to qwen, use `settings.qwen_api_key`/
  `settings.qwen_base_url`, raise `LLMError("QWEN_API_KEY missing")` when empty.
  Keep the SAME methods/helpers as the Gemini client.

1.3 **Router** (`src/services/chat/llm/router.py`): add an `alibaba`
  `ModelProvider` to `_PROVIDERS` with `qwen-plus`, `qwen-max`, `qwen-turbo`;
  add `QWEN_MODEL_IDS`; route `model_id.startswith("qwen")` → `QwenChat` in BOTH
  `get_llm` and `aclient_for` (aclient_for returns
  `openai.AsyncOpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url)`).

1.4 **Schema** (`src/services/chat/schemas/_core.py`): add `"alibaba"` to the
  `ProviderId` Literal (required — `ModelProvider.id` is validated at import).

1.5 **Tests**: clone `tests/test_router_gemini.py` → `test_router_qwen.py`
  (routing for the 3 ids, empty-key→`LLMError`, `aclient_for` base_url,
  `QWEN_MODEL_IDS`↔registry parity). Update `test_llm_router.py` provider
  count + ids (now includes `alibaba`). Monkeypatch the key; NO real network.

1.6 **Docs**: `docs/services/chat-features/06-llm-router.md` + dated changelog.

**Verify:** `.venv/bin/pytest src/services/chat/tests/ -q` green (watch for any
`test_adjacency_recall.py` failure — a prior `getattr` fix made
`_apply_section_parent_diversity` chapter-safe; do NOT revert it).

**Then orchestrator:** live smoke `qwen-plus` via `aclient_for` (confirms key +
region; if Singapore endpoint 401/403s, try `dashscope-us` or Beijing base_url).
Commit Task 1 with an explicit file list (NOT `git add -A` — repo has untracked
`docs/repos/*` embedded gits + `docs/Linkledin/`).

### Task 2 — Re-test deepseek-v4-pro with thinking DISABLED on the draft

The earlier deepseek-v4-pro rejection may be a config artifact. Memory
`deepseek-model-unreachable.md`: v4 ids default to THINKING → empty `content` +
slowness; fix = `extra_body={"thinking": {"type": "disabled"}}`.

2.1 Check whether the **draft path** (`deep_tutor.py` structured-stream call +
  the `aclient_for`/DeepSeekChat path) passes `extra_body` thinking-disabled.
  The ingestion client does; the chat/draft path likely does NOT.
2.2 If not, add a way to disable thinking for a deepseek draft (env or in the
  draft call when the model id starts with `deepseek`). Keep it scoped to draft.
2.3 This unlocks a fair deepseek-v4-pro entry in the battle at ~$0.0098/answer.

### Task 3 — The battle (orchestrator-run, measurement; no app code)

All providers exist after Task 1 → every candidate is selectable via
`stageModels={"draft": "<id>"}` over SSE. No code needed for the battle itself.

**Candidates (draft stage):**
- `gpt-5.4-2026-03-05` (baseline / incumbent)
- `qwen-plus`, `qwen-max`
- `gemini-2.5-flash` (re-test; pro was quota-blocked — retry if quota reset)
- `deepseek-v4-pro` (thinking disabled, per Task 2)
- groq: `openai/gpt-oss-120b` and `llama-3.3-70b-versatile`

**Method (reuse the established harness):**
- 4 fixed queries: `Define variance.`, `What is the bias-variance tradeoff?`,
  `What is overfitting?`, `Compare L1 and L2 regularization.`
- For EACH candidate × query: POST to `http://localhost:8766/api/chat` with
  `{"message": "...", "mode": "tutor", "stageModels": {"draft": "<id>"}}`,
  capture `retrieval_meta.timings` (esp. `draft_ms`) + `usage` (estTokens) from
  the SSE stream.
- **Run each candidate 3× on the bias-variance query** to measure DEPTH
  VARIANCE (the gemini-flash failure was inconsistency — one sample is not
  enough). Record min/max estTokens.
- Eyeball quality: pull the `definition` aspect — check decomposition
  (### Bias/### Variance/### MSE), clean LaTeX (`$$\\text{...}$$`, not mangled
  `\\$(X\\)$`), and articulation framing.

**Scorecard to fill:**

| Model | draft_ms | est tok (min–max ×3) | LaTeX | decomp | consistent? | $/answer | verdict |
|---|---|---|---|---|---|---|---|
| gpt-5.4 full | | | | | | ~0.042 | baseline |
| qwen-plus | | | | | | ~0.0055 | |
| qwen-max | | | | | | ~0.021 | |
| gemini-2.5-flash | | | | | | ~0.007 | |
| deepseek-v4-pro (no-think) | | | | | | ~0.0098 | |
| groq gpt-oss-120b | | | | | | ~0.001 | |
| groq llama-3.3-70b | | | | | | ~0.002 | |

**Backend note:** restart the backend so it picks up new keys + Qwen code
(`pkill -f 'uvicorn src.services.chat.api'` then
`.venv/bin/python -m uvicorn src.services.chat.api:app --host 0.0.0.0 --port 8766`
in background; wait for `/api/health` = 200). uvicorn `--reload` does NOT re-read
`.env` env vars added after process start.

### Task 4 — Decide + set the default

**Decision rule (in priority order):**
1. **Consistency** — reject any model whose estTokens swings >~1.5× across the
   3 runs (incomplete answers are unacceptable). This killed gemini-flash.
2. **LaTeX clean** — reject mangled-math models (this killed deepseek-v4-pro
   before; confirm whether thinking-disabled fixes it).
3. Among survivors, pick the **cheapest** that holds gpt-5.4-level depth +
   decomposition. That is the new `TUTOR_DRAFT_MODEL` default.
4. If none beats gpt-5.4 on consistency, KEEP gpt-5.4 full; the cheap models
   stay picker options.

Set the winner via `TUTOR_DRAFT_MODEL` (env in `.env`) + update the default in
`deep_tutor.py` `_DRAFT_MODEL_DEFAULT` only if you want it baked. Update doc 36
env table + changelog. Re-run the browser :5175 check (decomposition + LaTeX +
(i) modal) on the chosen model.

---

## 3 · Files map

| File | Task | Action |
|---|---|---|
| `src/core/config.py` | 1 | + `qwen_api_key`, `qwen_base_url` |
| `src/services/chat/llm/qwen_client.py` | 1 | NEW (clone gemini_client.py) |
| `src/services/chat/llm/router.py` | 1 | + alibaba provider, QWEN_MODEL_IDS, routing ×2 |
| `src/services/chat/schemas/_core.py` | 1 | ProviderId += "alibaba" |
| `src/services/chat/tests/test_router_qwen.py` | 1 | NEW (clone gemini test) |
| `src/services/chat/tests/test_llm_router.py` | 1 | provider count/ids |
| `src/services/chat/agents/deep_tutor.py` | 2 | deepseek draft thinking-disable (if needed) |
| `docs/services/chat-features/06-llm-router.md` | 1 | + alibaba/qwen |
| `docs/services/chat-features/36-deep-tutor.md` | 4 | draft default if changed |
| `docs/system/changelog.md` | 1,4 | entries |
| `.env` (gitignored) | 4 | `TUTOR_DRAFT_MODEL=<winner>` |
| `tmp` | 1 | DELETE (after keys confirmed in .env) |

## 4 · Commands

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
.venv/bin/pytest src/services/chat/tests/ -q            # after Task 1
# restart backend for live smoke + battle:
pkill -f 'uvicorn src.services.chat.api'; \
  nohup .venv/bin/python -m uvicorn src.services.chat.api:app --host 0.0.0.0 --port 8766 \
  > /tmp/statrag-backend.log 2>&1 &
# battle query (repeat per candidate id):
curl -sN -m200 -X POST http://localhost:8766/api/chat -H 'Content-Type: application/json' \
  -d '{"message":"What is the bias-variance tradeoff?","mode":"tutor","stageModels":{"draft":"qwen-plus"}}' \
  | grep -oE '"(timings|type": "usage)[^}]*\}'
```

## 5 · Risks / gotchas

- **Reasoning models** (qwen-max, deepseek-v4-pro) likely break the structured
  stream unless thinking is disabled — expect it, test with thinking off.
- **DashScope region**: if the Singapore base_url rejects the key, try
  `dashscope-us.aliyuncs.com` or Beijing `dashscope.aliyuncs.com`.
- **Groq structured output**: groq models may not honor `response_format`
  json_schema → JSON fallback path; verify the draft isn't truncated.
- **Cost numbers are estimates** — verify live before deciding.
- Commit with explicit file lists (untracked `docs/repos/*` are embedded gits).
- Keys are secrets: only in `.env`, never echo/commit; delete `tmp`.

## 6 · Definition of done

- Qwen provider merged, chat test suite green.
- deepseek-v4-pro re-tested with thinking disabled (viable or confirmed-dead).
- Battle scorecard filled (3-run variance per candidate).
- New `TUTOR_DRAFT_MODEL` default chosen by the decision rule (cheapest that
  holds consistency + LaTeX + depth), or gpt-5.4 retained with rationale.
- Docs + changelog updated; browser :5175 check on the chosen model; `tmp`
  deleted; memory updated with the battle verdict.
