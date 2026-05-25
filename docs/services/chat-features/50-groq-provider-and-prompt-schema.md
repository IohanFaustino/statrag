# 50 — Groq provider + prompt-schema invariant + LaTeX polish

**Date**: 2026-05-25
**Scope**: chat service (Groq integration), every system prompt in `src/services/chat/`, deep-tutor pipeline (Groq parity + polish stage)
**Status**: ✓ implemented

## Problem

Three intertwined gaps surfaced during A/B testing of Llama 4 Scout vs OpenAI nano in the deep-tutor pipeline:

1. **Groq integration was chat-only but underspecified end-to-end.** Stage code (`deep_tutor.py`, `orchestrator_workers.py`, `coverage.py`, `image_judge.py`) hardcoded an `AsyncOpenAI(api_key=settings.openai_api_key)` client — picking a Groq model from the SettingsPicker reached the right router but every downstream stage still hit OpenAI, surfacing as `BadRequestError: invalid model ID`. Even after wiring `_async_client(model_id)` correctly, Llama dropped backslashes inside JSON strings, so KaTeX rendered `mathbbE` as literal text instead of 𝔼.
2. **Prompts were inconsistently structured.** The 11 mode prompts (`prompts/{annotate,compare,figures,math,navigate,path,prereqs,quiz,research,roadmap,tutor}.py`) had `<role>` + `<task>` + `<rules>` but **no `<context>`**. The 9 deep-tutor stage prompts (`prompts/deep_tutor.py`) had **no XML structure at all** — they were plain prose. Inline agent prompts (`_GROQ_PROMPT_ADDENDUM`, `_LATEX_POLISH_PROMPT`, `_VISION_EXPLAIN_PROMPT`, image_judge tier-1/tier-2) were also plain text. Result: every model had to infer the role + I/O contract from prose, with smaller open-weights models (Llama 4 Scout) silently failing first.
3. **Math-block UI box stayed empty for Groq.** Llama emits all math inline (`$...$`), never `$$...$$` display blocks. The frontend's formula renderer picked up nothing from `math_blocks`.

## Solution

### A. Provider-aware stage clients (`router.py:aclient_for`)

Single factory in `src/services/chat/llm/router.py`:

```python
def aclient_for(model_id: str | None) -> openai.AsyncOpenAI:
    if model_id and model_id in GROQ_MODEL_IDS:
        return openai.AsyncOpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)
    if model_id and model_id.startswith("deepseek"):
        return openai.AsyncOpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
    return openai.AsyncOpenAI(api_key=settings.openai_api_key)
```

Called by `deep_tutor._async_client(model_id)`, `coverage._client(model_id)`, `orchestrator_workers.run_author_worker` (via `_async_client`). Stage call sites now thread the model id straight through.

### B. Per-provider output-token cap

Groq's Llama models cap `max_completion_tokens` at 8192 — exceeding it returns 400. `_cap_max_tokens(model_id)` clamps automatically:

```python
def _cap_max_tokens(model_id: str | None) -> int:
    if model_id and model_id in GROQ_MODEL_IDS:
        return min(_MAX_COMPLETION_TOKENS, _GROQ_MAX_COMPLETION_TOKENS)
    return _MAX_COMPLETION_TOKENS
```

Applied to every `max_tokens=`/`max_completion_tokens=` arg in the stream/parse/json_object tiers of `_stream_structured`.

### C. XML prompt-schema invariant (Zeroth law)

All 25 prompts rewritten so each has at minimum `<role>` + `<context>` + `<task>` tags, plus function-specific tags (`<rules>`, `<examples>`, `<output>`, `<structure>`, `<failure_mode>`, `<*_addendum>`). Locked in by:

- `docs/common ground/Agents/feature_Agent.md` Zeroth law — read on every feature_Agent invocation.
- `docs/system/invariants.md` invariant **#28**.
- `src/services/chat/tests/test_prompt_schema.py` — CI guard that walks every prompt constant and fails if `<role>`/`<context>`/`<task>` are missing.

### D. Groq-aware prompt addendum + LaTeX polish stage

When `m_draft in GROQ_MODEL_IDS`:

1. **Draft-time addendum** (`_GROQ_PROMPT_ADDENDUM` in `agents/deep_tutor.py`): appended to `DEEP_TUTOR_INSTRUCTIONS`. Spells out display-math (`$$ ... $$` on own line), double-escaped backslashes inside JSON strings, integer page numbers. Reduces but does not eliminate the backslash drop.
2. **Post-draft polish** (`_polish_latex_via_llm`): each aspect body is passed through OpenAI nano with a deterministic `<role>/<context>/<task>/<output>` repair prompt that adds missing backslashes inside `$...$` and `$$...$$` regions and changes nothing else. Polished aspects mirror back onto the `DeepTutorAnswer` before `_convert_to_tutor_answer`. Skipped entirely for OpenAI/DeepSeek drafts.
3. **Math-lift fallback** (`_lift_math_blocks_from_text`): when `DeepTutorAnswer.math_blocks` is empty, scan aspect text for standalone `$$...$$` blocks (and LaTeX-containing inline `$...$`), dedupe, populate up to 6 entries so the UI formula box renders.

## End-to-end verification (orchestrator workflow, Llama 4 Scout)

Question: *"Define variance with formula and MSE decomposition. Compare authors."*

| Metric | Result |
|---|---|
| Total wall time | 20.2s |
| Tokens (total) | 827 |
| `math_blocks` | **6** (was 0 pre-fix) |
| KaTeX display blocks rendered | 1 visible (others on-collapse-open) |
| `katex` elements total | 11 |
| Literal "mathbbE" in DOM | **false** |
| Literal "sigma" (unescaped) | **false** |
| Backend errors | 0 (strict-schema tiers fail, json_object tier succeeds, polish stage repairs) |
| Sources | 8 |

Sample rendered formula in the MSE Decomposition box:

> 𝔼[(y₀ − f̂(x₀))²] = Var(f̂(x₀)) + [Bias(f̂(x₀))]² + Var(ε)

All Greek letters, blackboard-bold, hats, and subscripts render correctly.

## Files touched

### Backend

- `src/core/config.py` — `groq_api_key`, `groq_base_url`, `groq_default_model`.
- `.env` — `GROQ_BASE_URL`, `GROQ_DEFAULT_MODEL` (key already present).
- `src/services/chat/llm/router.py` — `GROQ_MODEL_IDS` set, `aclient_for(model_id)`, provider registry entry.
- `src/services/chat/llm/groq_client.py` (new).
- `src/services/chat/cost.py` — Groq per-1M prices.
- `src/services/chat/schemas/_core.py` — `ProviderId` Literal extended.
- `src/services/chat/agents/deep_tutor.py` — `_async_client(model_id)`, `_cap_max_tokens`, `_GROQ_PROMPT_ADDENDUM`, `_LATEX_POLISH_PROMPT`, `_polish_latex_via_llm`, `_lift_math_blocks_from_text`, polish call in `_stream_draft`.
- `src/services/chat/agents/orchestrator_workers.py`, `agents/coverage.py`, `agents/image_judge.py` — model-aware clients + XML prompts.
- All 25 prompts in `src/services/chat/prompts/*.py` + the inline ones in `agents/*.py` — XML-schema rewrite.

### Frontend

- `web/src/types.ts` — `ProviderId` Literal extended.
- `web/src/components/ModelPicker.tsx`, `NodeModelDropdown.tsx` — Groq icon (`#F55036`).

### Tests

- `src/services/chat/tests/test_groq_client.py` (new) — unit.
- `src/services/chat/tests/test_groq_json.py` (new) — live, gated on `GROQ_API_KEY`.
- `src/services/chat/tests/test_llm_router.py` — Groq routing + registry sync.
- `src/services/chat/tests/test_prompt_schema.py` (new) — invariant #28 CI guard.

### Docs

- `docs/system/changelog.md` — 2026-05-25 entries (3).
- `docs/system/invariants.md` — invariants **#26** (Groq routing), **#27** (Groq prompt addendum + math-lift), **#28** (prompt XML schema).
- `docs/services/chat.md` — provider table + model list.
- `docs/common ground/Agents/feature_Agent.md` — Zeroth law + DoD checkbox.
- `docs/common ground/Elements/index.html` — §15 (Groq) + §16 (prompt schema + polish).
- `CLAUDE.md` — provider list expanded.

## Known residuals (logged, not blocking)

- Llama still occasionally emits citation `quote` text without backslashes (verbatim source fields). The polish stage only fixes the answer body, not the citation tooltips. Acceptable: the inline `[N]` markers still resolve; only the modal preview shows raw-text artifacts.
- Strict `json_schema` decoding still rejects Llama's `page_to: "44"` strings and missing optional fields. The `json_object` tier (tier 3 in `_stream_structured`) catches these. Citations come in slightly lower than the OpenAI path (3-4 vs 8-9).

## Why this won't regress

- **Prompt schema**: `test_prompt_schema.py` runs in CI; any new prompt without `<role>`/`<context>`/`<task>` fails fast.
- **Groq routing**: `test_groq_model_ids_match_provider_registry` in `test_llm_router.py` keeps `GROQ_MODEL_IDS` in lockstep with the provider registry.
- **Polish stage**: gated on `m_draft in GROQ_MODEL_IDS` — OpenAI/DeepSeek paths skip it, so latency for those is unchanged.
- **Cap clamp**: invisible to other providers — `_cap_max_tokens` falls through to `_MAX_COMPLETION_TOKENS` unless the model is in the Groq set.
