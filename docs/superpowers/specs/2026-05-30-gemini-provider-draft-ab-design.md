# Gemini Provider + Draft-Model A/B (Phase 4 candidate)

**Date:** 2026-05-30
**Status:** Approved (design)
**Context:** Phases 1–3 shipped; current draft winner = `gpt-5.4-2026-03-05`
(beat nano + deepseek-v4-pro in a measured A/B). This adds Google Gemini as a
provider and A/B-tests it as a draft candidate.

## Goal

Add a Google Gemini provider to the chat LLM layer following the existing
Groq/DeepSeek pattern, then A/B-test `gemini-2.5-flash` AND `gemini-2.5-pro` as
the tutor draft model against the current winner `gpt-5.4` full.

## Key facts

- Gemini exposes an **OpenAI-compatible endpoint**:
  `https://generativelanguage.googleapis.com/v1beta/openai/`. So a
  `GeminiChat(BaseLLM)` is a clone of `GroqChat`/`DeepSeekChat` — the OpenAI SDK
  with a custom `base_url` + API key. **No new dependency.**
- Key already in `.env` as `GEMINI_API_KEY` (gitignored; sourced from a temp
  key — never commit it).
- Risk (same as deepseek): the draft's `beta.chat.completions.stream` +
  `response_format` structured path may not be fully supported on Gemini's
  compat layer → it falls to the existing JSON fallback. The A/B reveals this.

## Scope

### 1 · `GeminiChat` client

- **Artifact:** new `src/services/chat/llm/gemini_client.py` (mirror
  `groq_client.py`); `src/core/config.py`.
- **Change:** `GeminiChat(BaseLLM)` using `openai.AsyncOpenAI(api_key=
  settings.gemini_api_key, base_url=settings.gemini_base_url)`. Config adds
  `gemini_api_key` (alias `GEMINI_API_KEY`) and `gemini_base_url`
  (default `https://generativelanguage.googleapis.com/v1beta/openai/`).
- **Error handling:** raise `LLMError("GEMINI_API_KEY missing")` when unset,
  exactly like `GroqChat`.

### 2 · Router registration + routing

- **Artifact:** `src/services/chat/llm/router.py`.
- **Change:** add a `google` `ModelProvider` to `_PROVIDERS` with models
  `gemini-2.5-flash` and `gemini-2.5-pro`. Route model ids starting with
  `gemini` → `GeminiChat` (add the rule alongside the deepseek/groq branches;
  mind that the groq ids are matched via an explicit set — add a `gemini`
  prefix check or a `_GEMINI_MODEL_IDS` set the same way).
- **`aclient_for` / `get_llm`:** ensure the model→client resolver used by the
  tutor stages (see `llm/router.aclient_for`) returns a Gemini-backed
  `AsyncOpenAI` for `gemini*` ids, so `stageModels.draft` / `TUTOR_DRAFT_MODEL`
  can select it.

### 3 · Make it selectable as the draft

- No deep_tutor change needed — Phase 2 already routes the draft via
  `TUTOR_DRAFT_MODEL` / `req.model` / `stageModels.draft` through
  `_resolve_stage_model` and `aclient_for`. Confirm a `gemini*` draft id flows
  end-to-end (resolver returns the Gemini client; structured-stream call either
  works or degrades to the JSON fallback).

## A/B test (run by orchestrator, not the agent)

Same 4 queries used for prior baselines (Define variance, Bias-variance,
Overfitting, L1 vs L2), via SSE with `stageModels={"draft": "<gemini id>"}`:

| Draft model | latency (draft_ms / total) | est tokens | LaTeX clean? | quality (articulation/decomposition) |
|---|---|---|---|---|
| `gpt-5.4` full (incumbent) | ~40s / ~85s | ~2800 | yes | strong |
| `gemini-2.5-flash` | ? | ? | ? | ? |
| `gemini-2.5-pro` | ? | ? | ? | ? |

Decide the draft default on the data, exactly as before. If a Gemini model
wins, set `TUTOR_DRAFT_MODEL`; otherwise keep `gpt-5.4` full and leave Gemini as
an available picker option.

## Verification

1. `pytest src/services/chat/tests/` green (+ a routing test: a `gemini*` id
   resolves to `GeminiChat`/Gemini base_url; missing key → `LLMError`).
2. A live smoke call to `gemini-2.5-flash` returns non-empty content (key works
   via the compat endpoint).
3. The A/B table above filled; winner chosen on latency + LaTeX + quality.

## Interconnected artifacts

| Aspect | File |
|---|---|
| Provider client | `src/services/chat/llm/gemini_client.py` (new) |
| Config | `src/core/config.py` (`gemini_api_key`, `gemini_base_url`) |
| Routing + registry | `src/services/chat/llm/router.py` |
| Schema (ProviderId) | `src/services/chat/schemas/_core.py` (`ProviderId` add `"google"` if it gates) |
| Per-feature doc | `docs/services/chat-features/06-llm-router.md`, `50-groq-provider-and-prompt-schema.md` |
| Changelog | `docs/system/changelog.md` |
| Tests | `src/services/chat/tests/` (router/provider tests) |

## Security

- `GEMINI_API_KEY` lives only in `.env` (gitignored). The `tmp` key file is NOT
  gitignored — delete it after the key is in `.env`; never commit either.

## Out of scope

- Frontend picker styling for the new provider (it appears via the registry;
  no bespoke UI work).
- Changing the default draft model — only done if Gemini wins the A/B.
