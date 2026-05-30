# Qwen (Alibaba) Provider + Draft-Model A/B

**Date:** 2026-05-30
**Status:** Approved (design)
**Context:** Draft-model A/B series. Incumbent winner = `gpt-5.4-2026-03-05`
(full). Prior tests: deepseek-v4-pro rejected (reasoning model breaks the
structured stream); gemini-2.5-flash inconsistent depth (kept as picker only).
This adds Alibaba Qwen via DashScope and A/B-tests it as the tutor draft.

## Pricing comparison (per 1M tokens; draft is output-heavy ~2800 out / ~35 in)

| Model | Input | Output | Ctx | Type |
|---|---|---|---|---|
| gpt-5.4 full (incumbent) | $2.50 | $15.00 | 1.1M | standard |
| qwen-plus (→3.6-plus) | $0.325 | $1.95 | 1M | standard |
| qwen-max (→3.7-max) | $2.50 | $7.50 | 1M | reasoning |
| qwen-turbo | $0.033 | $0.13 | — | flash |

`qwen-plus` output is ~7.7× cheaper than gpt-5.4 full — the meaningful cost
lever IF quality holds. `qwen-max` is a reasoning model (expect deepseek-pro
failure mode on the structured stream). `qwen-turbo` is flash-tier (expect
gemini-flash thinness).

## Goal

Add a Qwen provider (OpenAI-compat, mirrors the Gemini/Groq pattern), register
`qwen-plus`/`qwen-max`/`qwen-turbo`, then A/B `qwen-plus` + `qwen-max` as the
tutor draft against `gpt-5.4` full. Decide the default on the data.

## Key facts

- Qwen (DashScope Model Studio) exposes an **OpenAI-compatible endpoint**.
  International (Singapore): `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`.
  So `QwenChat(BaseLLM)` is a direct clone of `GeminiChat`/`GroqChat` (OpenAI
  SDK + base_url + key). **No new dependency.**
- Structured output: DashScope supports `response_format` json_schema with
  strict validation on the compat endpoint (so the draft's structured stream
  may work — the A/B confirms).
- Key in `.env` as `QWEN_API_KEY` (gitignored; from a temp key — never commit).

## Scope

### 1 · `QwenChat` client
- **New** `src/services/chat/llm/qwen_client.py` mirroring `gemini_client.py`:
  `openai.AsyncOpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url)`;
  raise `LLMError("QWEN_API_KEY missing")` when unset.
- **Config** (`src/core/config.py`): `qwen_api_key` (alias `QWEN_API_KEY`) +
  `qwen_base_url` (alias `QWEN_BASE_URL`, default the Singapore intl compat URL).

### 2 · Router registration + routing (`router.py`)
- Add an `alibaba` `ModelProvider` to `_PROVIDERS` with models `qwen-plus`,
  `qwen-max`, `qwen-turbo`.
- Add a `QWEN_MODEL_IDS` set + route `model_id.startswith("qwen")` → `QwenChat`
  in BOTH `get_llm` and `aclient_for` (mirror the gemini wiring exactly so a
  `qwen*` draft id resolves to a Qwen-backed `AsyncOpenAI`).
- `ProviderId` (`schemas/_core.py`): add `"alibaba"`.

### 3 · Selectable as draft
- No deep_tutor change — `TUTOR_DRAFT_MODEL` / `stageModels.draft` already route
  through `_resolve_stage_model` + `aclient_for`. Confirm a `qwen*` draft id
  flows end-to-end (works or degrades to the JSON fallback).

## A/B test (orchestrator-run, not the agent)

Same 4 queries via SSE with `stageModels={"draft": "<qwen id>"}`. Capture per
model: draft_ms / total, est tokens, LaTeX clean?, **depth consistency across
3 runs** (the gemini-flash failure was inconsistency, so measure variance, not
one sample).

| Draft | draft/total | tokens (×3 runs) | LaTeX | consistent? |
|---|---|---|---|---|
| gpt-5.4 full (incumbent) | ~40s/85s | ~2800 | yes | yes |
| qwen-plus | ? | ? | ? | ? |
| qwen-max | ? | ? | ? | ? |

Decision: if `qwen-plus` is consistently gpt-5.4-quality at ~1/8 output cost →
strong candidate for default (set `TUTOR_DRAFT_MODEL`). Else keep gpt-5.4 full;
Qwen models stay picker options.

## Verification
1. `pytest src/services/chat/tests/` green (+ routing test: `qwen*` →
   `QwenChat`/Qwen base_url; missing key → `LLMError`). No real network in tests.
2. Live smoke: `qwen-plus` returns non-empty content via the compat endpoint
   (confirms key + region; if Singapore 401s, try `dashscope-us`/Beijing).
3. A/B table filled (3 runs/model for variance); winner chosen.

## Interconnected artifacts
| Aspect | File |
|---|---|
| Client | `src/services/chat/llm/qwen_client.py` (new) |
| Config | `src/core/config.py` (`qwen_api_key`, `qwen_base_url`) |
| Routing/registry | `src/services/chat/llm/router.py` |
| Schema | `src/services/chat/schemas/_core.py` (`ProviderId` += `"alibaba"`) |
| Doc | `docs/services/chat-features/06-llm-router.md` |
| Changelog | `docs/system/changelog.md` |
| Tests | `src/services/chat/tests/test_router_qwen.py` (new) + `test_llm_router.py` (counts) |

## Security
`QWEN_API_KEY` only in `.env` (gitignored). The `tmp` file (holds google + Qwen
keys) is NOT gitignored — delete after extraction; never commit either key.

## Out of scope
- Frontend picker styling (appears via registry automatically).
- Changing the draft default — only if Qwen wins the A/B.
