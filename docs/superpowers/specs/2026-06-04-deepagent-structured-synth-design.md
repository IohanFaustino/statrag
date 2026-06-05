# Deep-agent structured synthesis — kill the schema-fill, enforce component formulas

**Date:** 2026-06-04
**Status:** design (awaiting review)
**Scope:** deep-tutor synthesis topology (`agents/ow_deepagents.py`, `agents/orchestrator_workers.py`, `ow_skills/synthesis/`). Builds two new synthesizer variants, A/B/C eval, ships the winner. No frontend/schema-field change.

## Problem

The orchestrator-deep (L3b) synthesis runs three LLM passes: parallel nano **workers** → deepagents **free-text synthesizer** → separate nano **`_schema_fill`** that re-expresses the text into the Pydantic `DeepTutorAnswer`. That third pass is **lossy**:
- It mangles math delimiters: clean `$…$` becomes `\$(…\)$` (only renders via a brittle frontend shim `normalizeMathDelimiters`).
- It flattens the C-style bullets / structure the synthesizer produced.
- Definitions come out **vague** with **no component-defining formulas** (e.g. bias/variance/MSE are described in words, not given as `$$\text{MSE}=\text{Bias}^2+\text{Var}+\sigma^2$$`).

## Findings (from the DeepAgents docs)

- **`create_deep_agent(..., response_format=DeepTutorAnswer)`** (or `ToolStrategy(schema=DeepTutorAnswer, handle_errors=True)`) makes the agent emit a **validated `DeepTutorAnswer` directly** at `result["structured_response"]`. This **eliminates `_schema_fill`** — the source of the mangling. The model writes JSON containing raw LaTeX strings; no lossy re-express. (deepagents 0.6.8 ✓)
- **`ToolStrategy`** works across providers (OpenAI/DeepSeek/Qwen/Gemini/Groq) — avoids the qwen `json_schema` hang; `ProviderStrategy(strict=True)` is OpenAI-only.
- **Subagents** can return typed JSON (`response_format=AuthorBrief` per subagent) but run **serially**; true parallel needs AsyncSubAgent + an Agent Protocol server (out of scope). Current nano workers already fan out in parallel via `asyncio.gather`.
- **Planning / memory / summarization** add nothing here (bounded one-shot synthesis); summarization is even risky (could drop citations/math). Leave defaults.
- **Skills instruct; `response_format` enforces.** Put the formula-demand in `SKILL.md`; guarantee structure via `response_format`.
- **Streaming caveat:** `structured_response` is only available when the agent finishes — no mid-run aspect streaming. The deep path is already ~45 s blocking, so we emit the final answer in one event (acceptable; documented).

## Approaches (A vs B vs C — eval decides)

| | Topology | New harness level |
|---|---|---|
| **A — Structured synth** | parallel nano workers → **1 deep agent, `response_format=DeepTutorAnswer` + enriched skill** (no `_schema_fill`) | **6** |
| **B — Subagent merge** | **1 deep agent**, N `author-analyst` subagents (`response_format=AuthorBrief`) → synthesize → `response_format=DeepTutorAnswer` (no separate workers, no `_schema_fill`) | **7** |
| **C — current L3b (baseline)** | workers → deepagents free-text → `_schema_fill` | 5 (shipped) |

## Components

### 1. Enriched synthesis skill — `ow_skills/synthesis/SKILL.md` (+ `references/formulas.md`)
Add hard rules (kept short; detail offloaded to `references/formulas.md`, loaded on demand):
- For a decomposition/tradeoff concept, emit one `### <Component>` per component whose **first bullet states the defining formula inline**, then a `### <central quantity>` with the `$$decomposition$$`. Example pattern (bias-variance):
  - `- **Bias** — $\operatorname{Bias}(\hat f)=\mathbb E[\hat f]-f$ — systematic error from too-rigid class`
  - `- **Variance** — $\operatorname{Var}(\hat f)=\mathbb E[(\hat f-\mathbb E[\hat f])^2]$ — sensitivity to the sample`
  - `### Trade-off` → `$$\operatorname{MSE}=\operatorname{Bias}^2+\operatorname{Var}+\sigma^2$$`
- Math delimiters: inline `$…$`, display `$$…$$`. **Never** plain-text math, never `\(`/`\$(`. The `description` frontmatter gains the keywords "LaTeX / formula / math" so the skill reliably matches.
- C-style bodies (bold lead + bold lead-in bullets) — carried from the prior cycle.

### 2. Approach A — `synthesize_structured` (new, `ow_deepagents.py`)
```
async def synthesize_structured(query, sources, briefs, *, model=None, figures=None)
    -> tuple[DeepTutorAnswer | None, int, int]
```
- Build the StoreBackend store with `/briefs/*.md` + `/skills/synthesis/SKILL.md` (+ `references/`), plus the figure bundle text.
- `create_deep_agent(model=ChatOpenAI(chosen), backend=StoreBackend, store=store, skills=["/skills/"], system_prompt=<draft C-style contract>, response_format=ToolStrategy(DeepTutorAnswer, handle_errors=True))`.
- Return `result["structured_response"]` (a `DeepTutorAnswer`) + token usage. No `_schema_fill`.

### 3. Approach B — `synthesize_subagents_structured` (new, `ow_deepagents.py`)
- `create_deep_agent(..., subagents=[{name:"author-<slug>", description, system_prompt, skills:["/skills/"], response_format=AuthorBrief} per author], response_format=ToolStrategy(DeepTutorAnswer, handle_errors=True))`.
- System prompt instructs: delegate per-author analysis to each subagent, then synthesize into the typed answer. No separate worker pass, no `_schema_fill`.

### 4. Routing — `orchestrator_workers.py` + `ow_harness.py`
- `ow_harness.py`: bump `_MAX_IMPLEMENTED_LEVEL` to 7; document levels 6 (A) and 7 (B).
- `run_orchestrator_workers`: add branches for level 6 → `synthesize_structured`, level 7 → `synthesize_subagents_structured`. On a non-None `DeepTutorAnswer`, return `(answer, aspects_from_answer)` directly (no `_schema_fill`). Any failure/None → fall back to the existing L0 synth. Figures forwarded (as in the prior cycle).
- Provider coercion: reuse the existing non-OpenAI→nano coercion already in the deep_synth branch.

### 5. Eval — `agents/ow_deepagents_compare.py` (extend)
Add metric functions + a small runner that executes levels **5, 6, 7** on a fixed query (the user's bias-variance tradeoff). Metrics per variant:
- `clean_math`: zero `\$(` / `\)$` artifacts in any aspect text (bool/count).
- `has_component_formulas`: regex for `$\operatorname{Bias}` / `Var` / `$$…MSE…$$` present in `definition`.
- `bullet_count`: `- **` occurrences (C-style density).
- `latency_s`, `in_tok`, `out_tok`.
Few calls: one query, one run per level (3 LLM runs total). Print a comparison table. Gated behind an env flag / pytest mark so it doesn't run in CI.

### 6. Winner wiring
After the eval, point the live `orchestrator-deep` path (the `deep_synth` branch / default level) at the winning function and set its default. Record the eval table + decision in the changelog + doc 56.

## Testing
- Unit (no network): `synthesize_structured` / `synthesize_subagents_structured` return the `structured_response` (monkeypatch `create_deep_agent` to a stub agent whose `invoke` returns `{"structured_response": DeepTutorAnswer(...)}`); assert the function returns it and forwards `figures`/`skills`.
- `ow_harness.py`: level parsing accepts 6/7, rejects 8.
- Eval metric functions: unit-test `clean_math` / `has_component_formulas` / `bullet_count` on fixture strings.
- SKILL.md contract: `references/formulas.md` exists; SKILL.md demands `$…$` + component formulas (string asserts).
- Regression: full `src/services/chat/tests/` green.
- Manual: run the eval (3 runs), then one live `orchestrator-deep` run on :5175 confirming clean inline math + bias/variance/MSE formulas in bullets.

## Docs lockstep
- `docs/services/chat-features/56-deep-synthesis-l3b.md` — levels 6/7, structured-output topology, eval table + winner.
- `docs/system/changelog.md` — entry. `docs/system/invariants.md` — note "deep synth emits typed DeepTutorAnswer directly (no schema-fill) on the winning level".
- No modal/pipeline-diagram change unless the winner changes the user-visible stage list (the synth box stays one node).

## Non-goals
- AsyncSubAgent / Agent Protocol server (parallel subagents) — out of scope.
- Planning/memory/summarization middleware — not enabled.
- Frontend changes — none (the frontend already renders clean `$…$`; this fixes the source).
