# Changelog & decisions log

Append-only. Latest at top.

## 2026-06-04 — OW harness ablation Plan B (L2/L3 A/B)
Re-baselined on scoped stats/econ sources + content-bearing fidelity. Added L2
structured-JSON brief handoff (production-wired, flag-gated) and L3 deepagents
synthesizer agent (eval experiment, lazy import, not a prod dep). 3-way A/B verdict:
L2 ≈ L0 (no effect); L3 +0.41 quality but −0.67 fidelity on a tiny sample → NOT shipped,
L0 stays default. deepagents uninstalled (no win). Level 4 (full subagents) deferred.

## 2026-06-04 — Orchestrator-workers harness ablation (Plan A)
Added `TUTOR_OW_HARNESS` (L0 baseline, L1 LangSmith tracing passthrough), an
`on_briefs` capture hook, a context-fidelity eval, and the eval-flow methodology
playbook (`eval-methodology.md`, doc 55). deepagents feasibility spike → FEASIBLE
(drives nano via ChatOpenAI; virtual filesystem works); L2/L3 deepagents conversion
deferred to Plan B. L0 baseline mediocre + partly confounded by all-book retrieval
pulling off-topic authors — Plan B scopes sources + refines the fidelity metric first.

## 2026-06-04 — Chained question-decomposition query planner
Added flag-gated 3-step planner chain (decompose→expand→consolidate) behind
`TUTOR_PLANNER_CHAIN` (default off), single-call planner as fallback. New prompts,
doc 54, and a 3-model eval harness. Downstream QueryPlan unchanged.

## 2026-06-03 — Facilitate teach model → nano (was qwen-plus)

Changed the facilitate **teach** stage default from `qwen-plus` to `gpt-5.4-nano-2026-03-17` in `_model_for` (`src/services/chat/agents/facilitate.py`); all facilitate stages now default to nano. Driven by a produce-model sweep on Hansen ch07 §7.2–7.5: nano won on **both** quality (LLM-judge overall 3.8 vs qwen 2.2) and cost — qwen-plus ran away to ~67k output tokens / ~85s per teach call (~30× nano cost) under the reasoning-variant prompt. groq `llama-3.3-70b` and `gemini-2.5-flash` were also low quality (≈1.95; gemini additionally free-tier 429'd). Per-stage `FACILITATE_<STAGE>_MODEL` / `stageModels` overrides still win. Reports: `docs/superpowers/eval/2026-06-03-facilitate-reasoning-models.md` (sweep), `…-v2.md` (reasoning A/B, +0.17). Tests: `test_facilitate_model_defaults_all_nano`, `test_facilitate_stage_model_override_wins`. The reasoning/CoT variant itself remains eval-only (not yet shipped); spec at `docs/superpowers/specs/2026-06-03-facilitate-reasoning-design.md`.

## 2026-06-02 — QA prompt standardization (feature 51)

**QA prompt standardization** — Q&A mode prompts (`QA_SCOPE_PROMPT`, `QA_GENERATE_PROMPT`, `QA_VERIFY_PROMPT` in `src/services/chat/prompts/qa.py`) retrofitted to the `<role>/<task>/<output_format>/<rules>` XML scaffold (invariant 28; same convention as tutor/chapter/facilitate). The three QA LLM calls (scope, generate, verify) now route through `apply_structured_output`, the per-model capability gate: native `json_schema` for capable models (gpt/gemini/qwen/kimi), else `json_object` plus a `<response_format>` hint. Per-call schemas: `QAScope`, `QAGenerateOut`, `QAVerifyOut` (the latter two added here). Additive only: pipeline shape (scope→retrieve→generate→verify), SSE contract, `QAAnswer` payload, and fail-open behaviour all unchanged. See [`docs/services/chat-features/51-qa-mode.md`](../services/chat-features/51-qa-mode.md).

## 2026-06-01 — Facilitate concept-map redesign (feature 53)

Redesigned `facilitate` mode to teach by **clarifying, not expanding**. The new pipeline in `src/services/chat/agents/facilitate.py` runs: parse+resolve → fetch (ordered by `page_from`) → per-section [map → adaptive sub-retrieval → teach → verify] → `FacilitateDigest`. The map node extracts key points and flags each concept as `"explained"` (inline) or `"referenced"` (needs sub-retrieval). Adaptive sub-retrieval (`fetch_concept_support`) escalates: same-author prior section (formal-statement boost) → same-author anywhere → other authors, stopping when score ≥ `CONCEPT_MIN_SCORE` (0.30). The teach node writes short paragraphs + bullet key-points + `[[cN]]` concept anchors (formula anchors use the same `[[cN]]` marker with `kind="formula"`; no separate `[[fN]]` namespace) (body must be shorter than source); `prior_context` is threaded forward. New schemas: `ConceptProvenance`, `ConceptAnchor`, `FacilitateBlock`, `FacilitateDigest` (in `schemas/output.py`). SSE emits `structured_output{schema:"FacilitateDigest"}` with stage keys `map`/`retrieve`/`teach`/`verify`. Frontend: `FacilitateDigestCard` + `ConceptModal` (KaTeX derivations for formula anchors); export flattens anchors to Markdown footnotes. Eval harness: `src/services/chat/eval/facilitate_eval.py` (`-m facilitate_eval`); ranked table at `docs/superpowers/eval/2026-06-01-facilitate-variants.md`. New env flags: `FACILITATE_MAX_CONCEPTS=5`, `FACILITATE_MAX_KEYPOINTS=6`, `CONCEPT_MIN_SCORE=0.30`, `FACILITATE_SUBRETRIEVAL=1`. `resume` is unchanged (still emits `ChapterDigest`). Invariant 32 added. See [`docs/services/chat-features/53-facilitate-concept-map.md`](../services/chat-features/53-facilitate-concept-map.md).

## 2026-06-01 — Book scope resolve + clarify (feature 52)

Added fuzzy book-reference resolution to `facilitate`, `resume`, and `qa` modes. A compact book catalog (slug · name · authors_short · field · chapter ids), built by `parse_catalog()` in `src/services/chat/books.py`, is injected into the parse-scope LLM prompt (`CHAPTER_PARSE_PROMPT`). The shared resolver `resolve_book()` in `src/services/chat/agents/_scope.py` returns `BookResolution{book_slug, book_confidence, book_candidates, chapter_id, requested_subtopics}`. Numeric section refs ("7.2 up to 7.4") are expanded deterministically by `expand_section_refs`. A confirm gate `maybe_clarify(res, catalog)` emits a new terminal SSE event `clarify` only on ambiguity or miss (`book_unknown`, `book_ambiguous`, `chapter_missing`); a confident single match runs the pipeline with no extra turn. A book selected explicitly by the user is always `book_confidence=1.0`. Kill-switch: `CHAPTER_CLARIFY=0`. New env flags: `BOOK_CONFIRM_CUTOFF=0.6`, `CHAPTER_CLARIFY=1`. Invariant 31 added. See [`docs/services/chat-features/52-book-scope-resolve.md`](../services/chat-features/52-book-scope-resolve.md).

## 2026-06-01 — Editable mode modals (qa / facilitate / resume)

Q&A, Facilitate, and Resume modes now have an editable `(i)` modal with a
per-stage model/provider switch (new `QAPipelineDiagram` + `ChapterPipelineDiagram`
components; `QAModeModal` remade; new `ChapterFacilitateModal` + `ChapterResumeModal`).
Overrides write the shared `stageModels` dict (disjoint stage keys; backend
`_model_for` already supported per-stage overrides). Added Gemini (`google`) and
Alibaba (`alibaba`) provider icons + `ProviderId` members. Frontend-only.

## 2026-05-31 — Added chapter modes (facilitate / resume)

Added `facilitate` and `resume` as two structural chat modes. Both traverse a chapter's sections in **chapter reading order** (`page_from`, then `section_id`) rather than by search relevance. Pipeline: parse-scope (extract book + chapter + subtopic names; fail-open to whole chapter) → fetch-chapter (Qdrant scroll, sorted structurally — no embeddings) → resolve-subtopics (substring then nano fuzzy match; empty = whole chapter) → map (per-section LLM call in order, threads `prior_context` forward) → stitch (connective intro/outro, never reorders) → ground (advisory grounding verdict). `facilitate` teaches each section in sequence; `resume` compresses it into a dense summary. Emits a `ChapterDigest` with an ordered `blocks[]` list. **Order-preservation is an enforced invariant** (invariant 30): blocks in `ChapterDigest` equal the fetched-section order and are never re-sorted downstream. All LLM nodes default to `gpt-5.4-nano-2026-03-17`; map dominates cost (one call per section); per-node override via `stageModels` / `CHAPTER_*_MODEL`. See [`docs/services/chat-features/52-chapter-modes.md`](../services/chat-features/52-chapter-modes.md).

## 2026-05-31 — Added punctual Q&A mode

Added `qa` as a second chat mode alongside tutor. Scope-extract → hybrid-retrieve → scoped-generate → grounding-verify pipeline; lean `QAAnswer` schema (no sections/figures/aspects); gpt-5.4-nano default on all LLM nodes; corpus-miss path emits honest no-coverage message with empty citations (never fabricates). ModeId, schemas, prompts, mode registry, router dispatch, cost table (gemini + qwen prices), frontend types, QAAnswerCard renderer, QAPipeline diagram, mode chip all implemented in lockstep. See [`docs/services/chat-features/51-qa-mode.md`](../services/chat-features/51-qa-mode.md).

## 2026-05-31 — Removed the 10 non-tutor chat modes

Removed the 10 non-tutor chat modes (compare/figures/quiz/navigate/prereqs/annotate/research/math/path/roadmap) across backend, frontend, and docs. Tutor (deep-tutor pipeline) and the mode-selection scaffold retained; ModeId collapsed to Literal['tutor']. Spec: docs/superpowers/specs/2026-05-31-remove-nontutor-modes-design.md.

## 2026-05-31 — Draft-model battle verdict → `qwen-plus` (battle Task 3+4)

Ran the multi-provider draft battle in-process (`scripts/draft_battle.py`) — the sandbox kills any bound uvicorn (exit 144), so instead of POSTing to `/api/chat` the harness retrieves real sources once per query (rerank on) then calls the draft stage directly per candidate, measuring wall-clock latency, output tokens, aspect-fill, and the `definition` aspect for LaTeX/decomposition eyeball. Bias-variance query run 3× per candidate to expose depth variance.

| Model | BV tok ×3 | swing | LaTeX | depth | $/answer | verdict |
|---|---|---|---|---|---|---|
| gpt-5.4-2026-03-05 | 1872–2117 | 1.13× | clean | 5–6/6 | ~0.0421 | baseline |
| **qwen-plus** | 1841–2248 | 1.22× | clean `$$…$$` | 4–5/6 | **~0.0055** | **WINNER** |
| qwen-max | 1235–1765 | 1.43× | mangled | 5/6 | ~0.021 | reject (LaTeX, 158s spike, length fails) |
| gemini-2.5-flash | 233–2180 | 9.36× | — | 5/6 | ~0.007 | reject (depth collapse) |
| deepseek-v4-pro | 2229–2514 | 1.13× | clean `$$…$$` | 5–6/6 | ~0.0098 | strong #2 / fallback |
| groq gpt-oss-120b / llama-3.3-70b | — | — | — | — | ~0.001–0.002 | reject (unparseable drafts) |

**Decision (cost-benefit per stage):** `TUTOR_DRAFT_MODEL=qwen-plus` (set in `.env`). Cheapest of the three survivors holding consistency (<1.5× swing) + clean LaTeX + decomposition; ~7.7× cheaper than the gpt-5.4 incumbent. Code default in `deep_tutor.py` stays `openai_model_full` as a safe fallback (a clone without `QWEN_API_KEY`/`.env` still works). `deepseek-v4-pro` kept as fallback/picker — Task-2 thinking-disable rescued it (clean LaTeX + 6/6 vs prior empty/broken rejection). Doc 36 env table updated. Browser :5175 visual check still pending (sandbox can't host the dev server).

## 2026-05-31 — Alibaba Qwen provider (draft-model battle prep)

Added an Alibaba Qwen provider to the chat LLM layer, cloning the Gemini OpenAI-compat pattern. No new dependencies — DashScope's compat endpoint (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`) accepts the `openai` SDK verbatim. Unlocks `qwen-plus`/`qwen-max`/`qwen-turbo` as selectable draft-stage models for the multi-provider draft battle.

**Artifacts changed:**
- `src/core/config.py`: added `qwen_api_key` (alias `QWEN_API_KEY`, default `""`) and `qwen_base_url` (alias `QWEN_BASE_URL`, default `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`).
- `src/services/chat/llm/qwen_client.py` (new): `QwenChat(BaseLLM)` — mirrors `GeminiChat`; raises `LLMError("QWEN_API_KEY missing")` when the key is unset; supports `response_format` pass-through (`strict=False`).
- `src/services/chat/llm/router.py`: added `alibaba` `ModelProvider` with `qwen-plus`/`qwen-max`/`qwen-turbo`; added `QWEN_MODEL_IDS` set; routed `model_id.startswith("qwen")` → `QwenChat` in both `get_llm` and `aclient_for`; updated module docstring routing table.
- `src/services/chat/schemas/_core.py`: added `"alibaba"` to `ProviderId` Literal (required since `ModelProvider.id` is typed by it).
- `src/services/chat/tests/test_router_qwen.py` (new): routing (parametrized over the 3 ids), key-missing error, `aclient_for` base_url, registry counts/ids, `QWEN_MODEL_IDS` ↔ registry match.
- `src/services/chat/tests/test_llm_router.py`: updated provider count assertion 4→5 and ids set.

**Tests**: full chat suite green (3 skips = `GROQ_API_KEY` not set). See `docs/superpowers/plans/2026-05-30-draft-model-battle.md` (Task 1).

## 2026-05-31 — DeepSeek thinking-disable on the chat/draft path (battle Task 2)

The earlier `deepseek-v4-pro` draft rejection (empty content, broken LaTeX, ~9× latency) was a config artifact: the chat `DeepSeekChat.stream` path never disabled thinking, unlike the ingestion client. v4 ids default to THINKING mode → output budget spent on hidden reasoning → empty `content`.

**Artifacts changed:**
- `src/services/chat/llm/deepseek_client.py`: added `_thinking_extra_body(model)` helper — returns `{"thinking": {"type": "disabled"}}` for every deepseek id except `deepseek-reasoner` (a genuine CoT model), gated by `DEEPSEEK_DISABLE_THINKING` (default `"1"`). `stream` now passes it as `extra_body` when applicable.
- `src/services/chat/tests/test_deepseek_thinking.py` (new): v4-pro/chat disabled, reasoner exempt, env-flag-off respected.
- `docs/services/chat-features/06-llm-router.md`: documented `DEEPSEEK_DISABLE_THINKING`.

**Live smoke**: `deepseek-v4-pro` with thinking off returns clean `content` (`"OK"`) — was empty before. Unlocks a fair `deepseek-v4-pro` entry in the draft battle at ~$0.0098/answer.

## 2026-05-30 — Google Gemini provider (Phase 4 prep)

Added a Google Gemini provider to the chat LLM layer following the Groq/DeepSeek OpenAI-compat pattern. No new dependencies — Gemini's compat endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`) accepts the `openai` SDK verbatim.

**Artifacts changed:**
- `src/core/config.py`: added `gemini_api_key` (alias `GEMINI_API_KEY`, default `""`) and `gemini_base_url` (alias `GEMINI_BASE_URL`, default `https://generativelanguage.googleapis.com/v1beta/openai/`).
- `src/services/chat/llm/gemini_client.py` (new): `GeminiChat(BaseLLM)` — mirrors `GroqChat` exactly; raises `LLMError("GEMINI_API_KEY missing")` when the key is unset; supports `response_format` pass-through.
- `src/services/chat/llm/router.py`: added `google` `ModelProvider` with `gemini-2.5-flash` and `gemini-2.5-pro`; added `GEMINI_MODEL_IDS` set; routed `model_id.startswith("gemini")` → `GeminiChat` in both `get_llm` and `aclient_for`; updated module docstring routing table.
- `src/services/chat/schemas/_core.py`: added `"google"` to `ProviderId` Literal (required since `ModelProvider.id` is typed by it).
- `src/services/chat/tests/test_router_gemini.py` (new): 10 tests — routing, key-missing error, `aclient_for` base_url, registry counts/ids, `GEMINI_MODEL_IDS` ↔ registry match.
- `src/services/chat/tests/test_llm_router.py`: updated provider count assertion 3→4 and ids set.

**Tests**: 593 passed (2 pre-existing failures in `test_adjacency_recall.py` unrelated to this change). See `docs/superpowers/specs/2026-05-30-gemini-provider-draft-ab-design.md` for A/B plan.

## 2026-05-30 — Phase-2: quality reinvestment (draft-model upgrade, related-framings facet, topic diversity)

Three targeted quality improvements that reinvest the budget freed by Phase-1.
See `docs/superpowers/specs/2026-05-30-tutor-phase2-quality-reinvest-design.md` for full rationale and A/B data.

**1 · Draft model → full (`gpt-5.4-2026-03-05`)** (`src/services/chat/agents/deep_tutor.py`)
Added `_DRAFT_MODEL_DEFAULT = os.environ.get("TUTOR_DRAFT_MODEL","") or settings.openai_model_full`.
`run_deep_tutor` now sets `default_model = req.model or _DRAFT_MODEL_DEFAULT` so the draft stage defaults to the full model when no picker model is explicitly selected. All other stages (planner/expansion, coverage, image_judge, synthesizer worker) still resolve to `settings.openai_model_nano` — only draft is affected. A/B: steady ~40s vs 18–134s spike on nano; stronger articulation + decomposition framing. Revert: `TUTOR_DRAFT_MODEL=gpt-5.4-nano-2026-03-17`. New env row in doc 36.

**2 · Related-framings facet** (`src/services/chat/prompts/deep_tutor.py`)
Extended `EXTRACT_CONCEPTS_BUDGET_PROMPT` facets contract: planner now ALWAYS adds one **related-framings facet** (other contexts/parent theories the concept belongs to beyond the obvious one) and a matching retrieval query. Updated the bias-variance example to include `"other contexts where the bias-variance tradeoff arises (e.g. regularization, model selection, ensemble methods)"` + query `"bias-variance tradeoff in regularization and model selection"`. No new LLM call; extra query flows into existing multi-query RRF pull. Updated doc 45.

**3 · Section-parent (chapter) diversity tiebreak** (`src/services/chat/agents/deep_tutor.py`)
Added `_apply_section_parent_diversity(sources, ranked_all, eff_top_n)` called after the author floor in `_density_select`. When all surviving sources share the same `chapter` field (same parent framing), the best dropped source from a different chapter is reinserted (at most one slot). Author-diversity remains primary. Pure-local; degrades silently when chapter metadata is absent. Updated doc 42.

**Tests**: 85 green (+10 new in `test_deep_tutor.py`: draft-model default × 2, related-framings prompt × 2, section-parent diversity × 3).

## 2026-05-30 — Phase-1 token cuts + cheap quality wins

Five independent efficiency changes to the deep-tutor pipeline. No topology change, no model change. See `docs/superpowers/specs/2026-05-30-tutor-phase1-token-cuts-design.md` for full rationale.

**1 · Vision-explain lazy default** (`src/services/chat/agents/deep_tutor.py`)
`TUTOR_DEEP_VISION_EXPLAIN` is now tri-state `{"1","lazy","0"}`, default `"lazy"`. `"1"` caps at the single top-ranked figure (was: up to 3). `"lazy"` and `"0"` return `{}` — figures render with caption+judge_reason (existing fallback, zero quality cost). Effect: −2–3 vision calls per typical turn.

**2 · Prompt diet** (`src/services/chat/prompts/deep_tutor.py`)
De-duplicated `DEEP_TUTOR_INSTRUCTIONS`: collapsed the `<structure>` restatement of the `### Bias/### Variance/### MSE` decomposition guidance (was repeated from the `definition` field spec) and condensed the FORMULAS inline-example block (now refers to `<math_format>` for display-equation + JSON-escaping syntax). All distinct behavioral rules preserved; `test_tutor_prompt_contract.py` unchanged and green. Token-budget regression guard added (`len < 18800` chars). Old length: 18167 chars; new length: 17029 chars (−1138 chars, ~−284 tokens).

**3 · Coverage gate** (`src/services/chat/agents/deep_tutor.py`)
Added a predicate before the `assess_coverage` call: `needs_coverage = len(facets) >= 4 or any("$" in f or "formula" in f.lower() for f in facets)`. Simple questions (< 4 facets, no formula/`$`) skip the extra nano call and log `"coverage: skipped (simple)"`. Fail-safe: empty facets → gate returns False (guard `bool(facets)` already skips). Effect: −1 nano call + bundle re-read on simple questions.

**4 · Citation regex robustness** (`web/src/components/views/TutorView.tsx`)
Replaced the single-number `^\[\d+\]` branch with a comma/dash-list+range matcher `^\[\s*\d+(\s*[,–-]\s*\d+)*\s*\]`. Expands `[1, 2]` → 2 pills, `[1–3]` → 3 pills, `[5]` → 1 pill. `[F1]` figure branch unchanged and still checked first. Malformed markers fall through to literal text. 9 new vitest tests in `TutorView.citations.test.tsx`.

**5 · Floor tuning** (`src/services/chat/prompts/deep_tutor.py`)
`tldr` 60–110 → 45–90 words (soften; was padding short answers); `applications` 260–360 → 300–360 words (raise; user-reported short answers). `example_intuition` 340–480 unchanged; other fields unchanged.

**Tests**: pytest 78 green (+5 new: vision tri-state × 2, coverage gate × 2, token-budget guard × 1); vitest 94 green (+9 citation tests).

## 2026-05-29 — Chat export upgraded to Zip (Markdown + images)

Follow-up to the Markdown export. Both download buttons now emit a **`.zip`** (Markdown + bundled figure images) instead of a bare `.md`. Still frontend-only — no backend route, no SSE/schema change, Chinese wall untouched.

**Architecture**: new `web/src/lib/exportZip.ts` — `extractImageUrls(md)` (pure; finds `![](…)` image URLs under `/api/`, `/img/`, `http(s)`, deduped, tolerates title attrs) + `imageFilename(url, ct)` (deterministic `<basename>-<hash>.<ext>`; reads the `?path=` query basename so figures get meaningful names) + `buildZipBlob(md, {docName}, fetchFn?)` (fetch each unique image as ArrayBuffer, add under `images/<name>`, rewrite **markdown-link-anchored** occurrences to relative paths — so a URL that is a prefix of another isn't corrupted — add `<docName>.md`, return `{blob, missing}`). Added `jszip` dep. `downloadMarkdown(filename, content)` generalized to `downloadBlob(filename, blob)`. App handlers are now async, always `.zip`, and wrapped in try/catch so a build failure can't become an unhandled rejection. Failed image fetches keep their link (logged, listed in `missing`, never fatal).

**Tests**: 14 vitest cases in `exportZip.test.ts` (url extraction + dedup + title-attr; basename of slash-path; `buildZipBlob` bundle/rewrite, dedup-fetch-once, 404-keeps-link, no-images md-only, prefix-URL-no-corruption) using a mock `fetchFn` and `JSZip.loadAsync` content assertions. Suite 85 green; `tsc --noEmit` clean.

**End-to-end verification** (browser, :5175, reopened the tutor "Define variance in one sentence." conversation, 8 sources, 2 figures): per-answer export → `statrag-define-variance-in-one-sentence-a01.zip` unzipped to `…-a01.md` + `images/image_rsrcD3R-….jpg` + `image_rsrcD3S-….jpg` (real JPEG bytes 3807/5392B), links rewritten to `images/…`, **zero `/api/` links left**. Topbar export → full-conversation zip with the same deduped images. Console clean.

## 2026-05-29 — Chat Markdown export (frontend-only)

Added a `.md` export for chat content at two granularities. The Topbar download button (left of the theme toggle) exports the **active conversation**; a small download icon at the end of each completed answer exports **that single answer**. Pure frontend — no backend route, no SSE/schema change; the transcript already lives in the client store, so the Chinese wall is untouched (no `src/` change).

**Architecture**: one new pure module `web/src/lib/exportMarkdown.ts` (block prose → `$$math$$`, figures, source chips; conversation header + per-turn headings; `downloadMarkdown` Blob helper) + `web/src/lib/exportStructured.ts` (faithful markdown for all 8 structured schemas — TutorAnswer, Quiz, NavigationList, DAG, Report, StudyPlan, Roadmap, AnnotatedReading — with a `json`-fence fallback). Wiring: `IconDownload` + Topbar button (`onExportConversation`/`exportDisabled`), per-answer icon in `MessageThread` (`onExportMessage`), handlers in `App.tsx` (`statrag-<slug>.md` / `statrag-<slug>-a<NN>.md`, title sanitized to one line, answer ordinal among assistant messages). In-flight/errored turns skipped from full exports; quiz option letters use `String.fromCharCode` (unbounded).

**Tests**: 18 vitest cases across `exportMarkdown.test.ts` + `exportStructured.test.ts` (blocks, math, figure-in-blockquote, sources, TutorAnswer/Quiz/StudyPlan/DAG/NavigationList, unknown-schema fallback, full-conversation ordering, skip-in-flight). `tsc --noEmit` clean; full suite 71 green.

**End-to-end verification** (browser, :5175, tutor "Define variance in one sentence.", Groq llama-4-scout, 8 sources): per-answer export → `statrag-define-variance-in-one-sentence-a01.md` rendered the faithful TutorAnswer (prose sections + numbered citations with author·book·chapter·section·quote + figures, **no JSON leakage**); Topbar export → `statrag-define-variance-in-one-sentence.md` with the header + `## You` + `## TUTOR · <model>` turns in order. Console clean, no errors.

## 2026-05-25 — Prompt-schema invariant + LaTeX polish stage + orchestrator parity

Feedback from an orchestrator-mode run: Llama draft was emitting `mathbbE` instead of 𝔼, and the formula box stayed empty for some answers. Two underlying problems surfaced.

**1. Prompts were inconsistently structured.** Mode prompts (annotate, compare, figures, math, navigate, path, prereqs, quiz, research, roadmap, tutor) had `<role>` + `<task>` + `<rules>` but no `<context>`. Deep-tutor stage prompts (extract concepts, planner, orchestrator, organizer, coverage, author worker, synthesizer addendum, critique) had **no XML structure at all**. Inline agent prompts (`_GROQ_PROMPT_ADDENDUM`, `_LATEX_POLISH_PROMPT`, `_VISION_EXPLAIN_PROMPT`, image_judge `_TIER1_PROMPT`/`_TIER2_PROMPT`) were also plain text. Result: every model — but especially smaller open-weights ones — had to infer the role + context + IO contract from prose, leading to dropped backslashes, missing schema fields, and inconsistent output shapes. **Fix**: every prompt in `src/services/chat/prompts/*.py` and `src/services/chat/agents/*.py` now uses the mandatory `<role>` + `<context>` + `<task>` tags, plus the function-specific tags (`<rules>`, `<examples>`, `<output>`, `<structure>`, `<failure_mode>`, `<*_addendum>`) per the new Zeroth law in `feature_Agent.md`. 25 prompts rewritten.

**2. LaTeX-polish stage.** Earlier per-feature commit added a Groq prompt addendum + math-lift fallback. Llama still dropped backslashes inside JSON strings on the orchestrator path. Replaced the regex-repair approach with a small post-draft LLM stage (`_polish_latex_via_llm` in `deep_tutor.py`) that runs **only** when `m_draft in GROQ_MODEL_IDS`. Each aspect body is passed through OpenAI nano with a deterministic `<role>/<context>/<task>/<output>` repair prompt that adds missing backslashes inside `$...$` and `$$...$$` regions and changes nothing else. Polished aspects are mirrored back onto the `DeepTutorAnswer` before `_convert_to_tutor_answer`.

**End-to-end verification** (orchestrator workflow, Llama 4 Scout, "Define variance with formula and MSE decomposition. Compare authors."): 6 math_blocks, all LaTeX commands render correctly (σ², 𝔼, Var(X), f̂, Bias, ε), MSE decomposition shows in a dedicated math box, 20.2s/827 tokens total. Backend 568 pytest pass; lambda fixtures in `test_orchestrator_workers.py` + `test_query_planner_coverage.py` updated to accept the new `_async_client(model_id)` signature.

**Workflow rule (carried into `feature_Agent.md`)**: a logic change is incomplete until every prompt it touches is XML-tagged. New invariant **#28** + `feature_Agent.md` Zeroth law lock it in so this slip cannot recur.

## 2026-05-25 — Groq tutor parity (LaTeX + math_blocks)

Follow-up to the Groq integration. A/B comparison (`gpt-5.4-nano` vs `meta-llama/llama-4-scout-17b-16e-instruct` on "Define variance with the formula and explain the MSE decomposition.") surfaced three divergences:
1. **No `math_blocks`**: Llama defaulted to inline `$...$`, never `$$...$$`. UI formula box stayed empty.
2. **Dropped LaTeX backslashes in JSON**: Llama emitted `sigma` instead of `\sigma`, `hat{\theta}` instead of `\hat{\theta}` — backslash escaping unreliable in `json_object` mode.
3. **Under-citation**: 3 citations vs 8 baseline; strict json_schema rejections cascaded to the lenient json_object fallback.

**Fix (A + B):**
- **A. Groq-specific prompt addendum** (`_GROQ_PROMPT_ADDENDUM` in `deep_tutor.py`): appended via `_maybe_append_groq_addendum(prompt, model_id)` to `_stream_draft`'s system message when `draft_model in GROQ_MODEL_IDS`. Spells out display-math + backslash + citation rules with concrete escaped examples.
- **B. Math-lift post-processor** (`_lift_math_blocks_from_text`): safety net. When `deep.math_blocks` is empty, scans aspect text for standalone `$$...$$` blocks (and falls back to substantial inline `$...$` containing LaTeX commands), de-duplicates, returns up to 6 entries. Triggered in `_finalize_tutor_answer`.
- **Result**: Groq math_blocks 0 → 4; LaTeX backslashes now correct (`\mathrm{Var}`, `\hat{\theta}`, `\mathbb{E}`); definition body uses `$$ ... $$` on own lines. Citations 3 → 4 (still below OpenAI's 8 — residual gap, not blocking).

Routing fixes that this depended on (also in this commit):
- `src/services/chat/llm/router.py:aclient_for(model_id)` — provider-aware AsyncOpenAI factory. Used by `deep_tutor._async_client(model_id)`, `coverage._client(model_id)`, and `orchestrator_workers.run_author_worker` so stage calls reach the right provider's `base_url` + key.
- `_cap_max_tokens(model_id)` — clamps Groq stage calls to the 8192 `max_completion_tokens` ceiling (Llama models 400 otherwise).

## 2026-05-25 — Groq provider (chat-only, native JSON trusted)

Added Groq as a third chat-LLM provider. Reuses the `openai` SDK pointed at `https://api.groq.com/openai/v1`, mirroring the DeepSeek pattern. Scope is **chat-only** — ingestion (`src/ingestion/llm_client.py`) is unchanged.
- **Models exposed**: `meta-llama/llama-4-scout-17b-16e-instruct` (Groq default), `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`.
- **Routing**: `src/services/chat/llm/router.py` gains an explicit `GROQ_MODEL_IDS: set[str]` (membership, not prefix) — avoids collision with OpenAI-hosted `openai/*` IDs.
- **JSON mode**: Groq's native `response_format` (`json_object` / `json_schema`) is passed through verbatim — no DeepSeek-style coercion to nano. Verified live: `llama-4-scout-17b` and `llama-3.3-70b` pass; `openai/gpt-oss-20b` xfails (reasoning prefix tokens trip the validator) — orchestrator repair loop handles fallback.
- **Cost table**: `src/services/chat/cost.py` updated with conservative per-1M Groq prices.
- **Schema**: `ProviderId` Literal extended in `src/services/chat/schemas/_core.py` + `web/src/types.ts`.
- **Frontend**: Groq icon (`#F55036` rounded square w/ "G") added to `ModelPicker.tsx` + `NodeModelDropdown.tsx`.
- **Env**: `GROQ_API_KEY`, `GROQ_BASE_URL`, `GROQ_DEFAULT_MODEL` in `.env`. Config fields in `src/core/config.py`.
- **Tests**: `test_llm_router.py` extended (Groq routing, gpt-oss disambiguation, registry/`GROQ_MODEL_IDS` sync); new `test_groq_client.py` (key required, AsyncOpenAI wiring, response_format builder); new `test_groq_json.py` (gated live integration). Backend **576 pass**; tsc clean; **53 vitest pass**.
- **New invariant**: #26 — Groq model IDs route via membership in `GROQ_MODEL_IDS`; native JSON mode is trusted (no nano coercion); repair loop handles validator rejections.

## 2026-05-22 — §13 Detached, resumable streaming (runs survive conversation-switch)

**Problem:** sending a query, then switching conversation, killed the in-flight answer and lost it entirely. Two layers: the frontend held ONE `useChat` reducer and `loadConversation` aborted the `fetch` + wiped state on switch; the backend `chat_event_gen` was driven by the SSE connection, so the client abort made `sse-starlette` cancel the generator task — and the assistant row is persisted only *after* the generator completes.

**Fix:** detach generation from the connection + make the stream replayable by `seq`.
- **Backend** — new `src/services/chat/runs.py` (stdlib-only, Chinese-wall clean): `start_run(conv_id, source_factory)` spawns a background `asyncio.Task` that drains `chat_event_gen` into a per-conversation event buffer (each event tagged a monotonic `seq`) and fans out to subscriber queues; it runs to completion + persists even with zero subscribers. `subscribe(conv_id, after_seq)` replays buffered `seq>after` then streams live to a `done` sentinel (dedup by `seq`). TTL-GC 300s after finish; ≤1 active run/conv. `chat_event_gen` now yields raw event dicts; SSE `event/id/data` framing moved to `_frame`/`_sse_from_run`. New routes: `GET /api/chat/{id}/stream?after=N` (resume) + `GET /api/chat/{id}/status`. `POST /api/chat` with a `conversationId` → `start_run` + subscribe from `after=0`; without one → legacy connection-bound stream (unchanged).
- **Frontend** — `web/src/state/chat.ts` becomes a multi-conversation store (`byConv` keyed by convId + `active`), each slice tracking `lastSeq`; per-conv `AbortController` map; **switching no longer aborts** — the background `fetch` keeps reading into its hidden slice. `loadConversation`: if a slice is already streaming locally, just show it; else hydrate persisted, `GET status`, and if active append a placeholder + open the resume stream from `after=0`. Sidebar shows a pulsing "still generating" dot (`streamingIds`). `types.ts` `ChatEvent` gains `seq?`. `sse.ts` adds `streamResume` + `fetchRunStatus`.
- **Render-loop fix:** `loadConversation` reads the store via a `useRef` snapshot (not `store.byConv` in deps), so App's deep-link effect no longer re-fires every token (was spamming `/status` ~70×/turn).
- **Verified.** Backend `pytest` pass incl. new `test_runs.py` (8); `tsc --noEmit` clean; `vitest` 46 pass incl. `chat.test.ts` (6). Browser on :5175: sent in conv A → switched away → A's run kept advancing (`seq` 942→1457) with the sidebar dot → switched back, complete + persisted. Reload on an active conv replayed it (one `/status` + one `/stream?after=0`, no loop); post-reload console clean. Backend resume contract via curl: `after=0` monotonic replay from seq 1, `after=N` tails from seq N+1. New invariant **#25**.
- **Known limit:** runs are in-memory/process-local — a backend restart loses an in-flight run (persisted turns survive via SQLite).

## 2026-05-22 — §14b Draft/synthesis: invited to be extensive

Follow-on to §14. Raised the draft/synthesizer ceiling `TUTOR_DEEP_MAX_TOKENS` 6000 → **8000** (covers both `_stream_structured` draft and the orchestrator synthesizer) and added a **BE EXTENSIVE** preamble — per-field ranges are MINIMUMS, not caps; when sources support it, write more (more subsections, deeper mechanism, more cited cases); do not self-truncate. Verified live (bias-variance): definition 358w / example_intuition 747w / applications 323w / further_reading 156w (~1689w total), `further_reading` ends cleanly = no truncation; draft ~30s. Tests: `test_draft_knobs_defaults` (8000), `test_structure_requires_subsection_headers` asserts the extensive directive. 559 backend pass.

## 2026-05-22 — §14 Denser subsections (explain the problem + where it fits)

§12's `### ` subsections were thin (~40-60 words each): the fixed per-aspect word budgets were split across more headers, and the structure rule capped each subsection at "1-4 sentences" — cases/applications stated a fact without explaining the problem or where the concept fits. Prompt-only fix (no schema/frontend):
- Raised per-aspect budgets: `definition` 150-220 → **280-380**, `example_intuition` 220-320 → **340-480**, `applications` 150-220 → **260-360**.
- Structure rule: per-subsection cap "1-4 sentences" → SUBSTANTIVE **3-5 sentences**; added a global **DEPTH OVER BREVITY** directive — each subsection must explain (a) the problem it addresses, (b) the mechanism, (c) where it fits in the concept/theory/practice.
- Each application + example case is its own `### ` subsection following Problem/setting → method → where the concept fits.
- `TUTOR_DEEP_MAX_TOKENS` 4000 → **6000** so the denser answer is not truncated (≈ +latency on an already ~30-50s answer).
- Verified live (bias-variance): definition 272 w / example_intuition 759 w / applications 338 w (was ~200 w each); application cases now read "Problem/setting: Wooldridge considers… compare two estimators of $\beta_1$… if $\beta_2\neq0$, omitting $x_2$ induces bias" — problem + mechanism + fit, with formulas.
- Tests: updated `test_draft_knobs_defaults` (6000); `test_structure_requires_subsection_headers` now asserts the depth directive. **559 backend pass.**

## 2026-05-22 — §12 Subsection headers + citation hyperlink fix

Three refinements (common ground §12). Provider-independent; verified on the OpenAI model (deepseek-v4-pro is unreachable in this env — see note).
- **Block F — citation hyperlinks connect to sources.** Two causes: clicking a `[N]` pill set `#cite-N` but a repeat click fired no `hashchange` (no scroll); and models (esp. the deepseek router) emitted inline markers without a matching `citations` entry, so the pill had nothing to link. Fixes: (a) server `_ensure_marker_citations(text, enriched, sources)` guarantees every inline `[N]` has a source-linked citation (synthesized from sources in marker order when the model under-cites); (b) frontend `[N]` pill gets an explicit `onClick` → opens the Sources panel + scrolls/highlights `#cite-N` regardless of hash state. Router parse also salvages partial payloads.
- **Block G — left-aligned subsection headers instead of bullets.** Aspect bodies now use `### ` subsection headers (no toggle, no bullets), one per perspective. Definition → `### Bias`, `### Variance`, `### MSE` (decomposition + how each affects the error term); example_intuition → `### ` per case + `### The intuition`; applications → `### ` per cited case. `prompts/deep_tutor.py` structure rules + definition spec rewritten; `TutorView.tsx` parses `### ` → `<h3>` block (`splitIntoBlocks`/`groupSections` keep h3 in the section body, h2 still starts sections).
- **deepseek note:** user set the active model to `deepseek-v4-pro`; that id is not reachable at the live deepseek API here (draft stream empty / 120s hang), so verification used the OpenAI model. Both fixes are prompt/frontend, provider-independent.
- Verified live + **browser on :5175**: Definition shows `### Bias/Variance/MSE` with `MSE = bias²+variance+σ²`; Example & Intuition shows per-case subsections + "The intuition here is…"; Applications shows cited cases (Ridge vs. OLS, smoothing-spline, double descent); clicking `[1]` opened the Sources panel and highlighted reference [1]. All inline markers (1-4) had matching citations.
- Tests: `test_structure_requires_subsection_headers`, updated `test_definition_framing_and_buildup_contract`, `test_ensure_marker_citations_fills_gaps` + `_noop_without_sources`, frontend `splitIntoBlocks — §12 ### subsection headers`. **551 backend pass; tsc clean; 40 vitest pass.**

## 2026-05-22 — §11 Long-context organizer + real application cases (formulas/MSE fix)

Follow-up to §10 on two residual gaps: Definition gave no bias/variance formulas and never defined MSE (central to the figure); Applications listed generic domain labels, not real cases. Common ground §11.
- **Regression fix (all draft modes):** §10 Block B told `definition` to defer formulas to `formal_statement`, but that field is empty when no numbered theorem exists — so formulas had no home. `definition` now MUST write each component's formula + the central decomposition (e.g. MSE = bias² + variance + irreducible) inline, even when the quantity (MSE) was not named in the question but appears in the sources/figure. Verified live on the default path: bias `$\mathbb{E}[\hat\theta-\theta]$`, variance `$\mathrm{var}(\hat\theta)$`, and the MSE decomposition now render.
- **Block D — long-context organizer:** new `organize` drafting workflow (alongside `single`/`orchestrator`). Hands a large, token-budgeted candidate pool (`_build_organize_pool`: rerank to `TUTOR_ORGANIZE_POOL`=60, density-ranked sources first, trimmed to `TUTOR_ORGANIZE_MAX_TOKENS`=120k by ~chars/4, actual tokens logged) to `TUTOR_ORGANIZE_MODEL` (default `deepseek-v4-pro`) with `ORGANIZER_PREAMBLE` instructing it to scan everything and pull formulas, the decomposition, and real cases into the fields. **Augment, not replace:** density-rank still runs, so author-diversity + figure co-location are unaffected. Best-effort: organize→single fallback. Router parse hardened to salvage partial payloads / fall back cleanly on empty. `tutorWorkflow` request literal + `PipelineDiagram` dropdown + `tutorPipeline.ts` node desc updated.
- **Block E — real application cases:** planner now always emits an application-case facet + query (so the pool contains real cases); `applications` prompt requires a cited SPECIFIC case (named method/dataset/study), forbids bare domain labels, honest "no concrete applied case" fallback. Verified live (default path): Applications now cites James et al. (U-shape/double-descent) and Wooldridge's estimator comparison.
- **Honesty notes:** (a) `deepseek-v4-pro` is not reachable as a real model in this environment (forward-dated id) — the organize path streamed empty and **fell back to the single draft** (which produced a complete, correct answer), so organize is implemented + safe but NOT exercised end-to-end here; deepseek's real context window is unverified, hence the token-budget guard. (b) `rag-verify` currently FAILS on **invariant 2** (`page_from=-1`, 28/50 sampled `introduction_textbooks` points) — a PRE-EXISTING ingestion-payload condition, NOT caused by §11 (which never touches ingestion). Flagged for a separate fix.
- Tests: `test_definition_formulas_have_a_home_contract`, `test_organizer_preamble_contract`, `test_organize_workflow_resolves`, `test_build_organize_pool_token_budget`, `test_planner_emits_application_case_facet`, `test_applications_real_cases_contract`. **549 backend pass; tsc clean; 39 vitest pass.**

## 2026-05-22 — Answer coherence, Block C: schema (merge intuition+examples, rename trade_offs→applications)

Final block; common ground §10 → ✓. Schema-touching, ~14 files. The deep-tutor answer is now a 6-aspect set: `tldr, definition, formal_statement, example_intuition, applications, further_reading`.
- **Merge**: `intuition` + `examples` → single `example_intuition` ("Example & Intuition"), a three-move field: describe three cases → analyse the three → literal "The intuition here is that …". Prompt, `DeepTutorAnswer`, `ASPECT_HINT`, `ASPECT_HEADINGS`, `image_judge` hint enum + descriptions, `App.tsx` heading map, and the example-relevance audit (`_score_example_relevance`/`_embed_relevance`, now scored vs definition+formal_statement) all updated.
- **Rename**: `trade_offs` → `applications` everywhere (schema key, `ASPECT_HINT`, `image_judge`, headings, frontend). Heading "Applications" was already shown in Block B; now the key matches.
- **Strict-output safety**: all fields stay required; `formal_statement` omission remains render-side (empty string + `assemble_markdown` skip). New invariant 22 supersedes the Block-B note.
- Verified live + **browser (Chrome on :5175)**: bias-variance answer rendered exactly Introduction → Definition → **Example & Intuition** (Underfitting/Optimal/Overfitting → "Analyzing…" → "The intuition here is that…" → "Why these cases fit:") → **Applications** (econometrics / machine learning / model validation) → Further reading. Formal statement absent (no numbered def). New schema accepted by OpenAI structured output — **no 400, no fallback**; backend log 0 errors.
- Tests: 6-aspect set propagated across `test_deep_tutor`, `test_tutor_prompt_contract` (+ `test_example_intuition_merged_field_contract`), `test_image_judge`, `test_image_judge_quality` adjacency map, `test_orchestrator_workers`. **544 backend pass, 1 deselected; tsc clean; 39 vitest pass.**

## 2026-05-22 — Answer coherence, Block B: prompt content (definition build-up, conditional formal statement, Applications)

Prompt-content rewrite of three aspects (no schema break; key rename deferred to C). Common ground §10.
- **Definition** (`prompts/deep_tutor.py`): must OPEN WITH A FRAMING SENTENCE, then BUILD UP IN ORDER (define each named component — bias, then variance — before the relationship), then a graphical hand-off sentence if a figure is attached. Was a bare bullet dump with no lead-in.
- **Formal statement**: now CONDITIONAL — emitted only when a source has a numbered/labelled statement ("Conforming to Definition X.Y.Z, …" + verbatim blockquote); otherwise an **empty string** (heading dropped by `assemble_markdown`). Removed the old "INDIRECT WHEN NOT — write it yourself" fallback that made the section always appear. Field stays required (strict-safe). New invariant 22.
- **Trade-offs → Applications**: `ASPECT_HEADINGS["trade_offs"]` = "Applications"; prompt rewritten to corpus-grounded use-cases grouped by domain ("**In marketing:** …", "**In quantitative finance:** …"), invent-nothing. Frontend heading map (`App.tsx`) + mode description (`tutorMode.ts`) synced.
- Verified live (bias-variance, econometrics corpus): Definition opened "We first define the two error sources—bias and variance—then connect them … and finally explain how the tradeoff is visualized"; Formal statement empty → heading correctly absent; Applications grouped by Econometrics / Nonparametric smoothing (corpus-real, not invented).
- Tests: `test_definition_framing_and_buildup_contract`, `test_applications_grouped_by_domain_contract`, `test_aspect_heading_renamed_to_applications`, updated `test_formal_statement_verbatim_contract` + heading list. **543 backend pass; tsc clean; 39 vitest pass.**

## 2026-05-22 — Answer coherence, Block A: draft size + temperature knobs

Responses were short and the main draft path ran at an uncontrolled temperature. Tracing the draft calls in `deep_tutor.py`: the OpenAI **structured** path (`beta.chat.completions.stream`/`parse`) passed **no** `temperature` → model default (~1.0); only the deepseek router + json fallbacks used `0.2`. So creativity was un-steered and output capped at 2800 tokens.
- `TUTOR_DEEP_MAX_TOKENS` default **2800 → 4000** (code now matches the value docs already listed).
- New `TUTOR_DEEP_TEMPERATURE` (default **0.4**) applied to all draft paths: structured stream, router, json last-resort. Moderate temp = more factual than the prior ~1.0 main path, still enough creativity to connect concepts across sources. Plan/extract/judge/coverage stay `0.0`.
- Reasoning-model guard: the structured-stream call carries the temp; the `parse()` fallback omits it, so a temp-reject degrades structured→parse(no temp)→json cleanly instead of cascading to a 400.
- Tests: `test_draft_knobs_defaults`, `test_draft_knobs_env_override`. Full chat suite green.
- First of three blocks (common ground §10); B = prompt content, C = schema (merge intuition+examples, rename trade_offs→applications).

## 2026-05-21 — Author cap honored end-to-end (set 6 → got 3 fix)

Picking 6 authors still returned ~3. Three independent ceilings, all below 6 (documented `index.html` §9):
1. **Hard cap clamped 6→5** — `_DIVERSITY_MAX` default `max(_DIVERSITY_TARGET,5)` → **`max(…,6)`**.
2. **Section budget was the real ceiling** — `diversify_section_keys` returns ≤ `top_sections`=4 keys, so max 4 authors regardless of target. Fix: `_density_select` computes `eff_sections = max(top_sections, target_authors)` and uses it for both the diversify slot count and the Plan-B fill bound.
3. **Author-blind final rerank** trimmed to `_FINAL_TOP_N`=8 by relevance only, collapsing the picked authors to ~3. Fix: widen the cut to `max(final_top_n, target_authors)` then an **author-aware floor** — if the trim left fewer distinct authors than the target, top up with the best dropped chunk of each missing author, **budgeted to `target_authors - kept` so it never overshoots** the target. Verified on the live pool (23 authors available for the topic): target 2→4, 3→4, 4→4, 5→5, **6→6** (low targets land at 4 because the top-relevant sources already span 4 authors — relevance-preserving, not floor overshoot).
- Still bounded by distinct authors present in the candidate pool (honest corpus limit; logged via `distinct_authors_in_result`).
- Tests: `test_resolve_diversity_fixed_6_not_clamped`, `test_density_select_scales_sections_to_target` (6 authors → 6 sections), `test_density_select_corpus_limit_honest` (3 available → 3, no padding). **537 pass.**

## 2026-05-21 — Recall upgrades: adjacent-section expansion + TF weight + author cap

Three recall improvements (documented in `docs/common ground/index.html` §8).

- **Adjacent-section expansion** — `density._fetch_neighbor_chunks`: for each selected section, pull the nearest **sibling** sections before/after (same parent `section_id`, via `page_from` reading order within a page band) as low-score candidates; `deep_tutor._density_select` appends them and the **existing cross-encoder rerank + `final_top_n` cut is the gate** (no threshold). Env `TUTOR_NEIGHBOR_EXPAND` (1). Coverage's neighbor intent is satisfied at this stage (neighbors are candidates before the coverage check).
- **Term-frequency weight** — exposed `density._section_score`'s concept-TF weight as `TUTOR_DENSITY_ALPHA` (0.6). (True BM25/sparse reweighting deferred — Qdrant native RRF is unweighted.)
- **More authors** — `_DIVERSITY_MAX` default 4 → **5**; planner `perspectives` prompt nudged to be generous for broad/comparative questions; dropdown gains **5/6 authors**.
- Frontend: rerank node relabelled "Density select + rerank + adjacent sections".
- Tests: `test_adjacency_recall.py` (sibling/order/dedup/graceful + cap). **535 backend pass**, tsc 0, 39 vitest. Verified in-browser: "What is the bias-variance tradeoff?" formal statement now shows **both** `Bias(θ̂)=E(θ̂)−θ` AND `Variance(θ̂)=E(θ̂²)−(E(θ̂))²` (the previously-missing variance formula); 8 sources; 0 service errors.

## 2026-05-21 — Modal diagram made faithful to the common-ground graph

The interactive pipeline diagram had been left as a simplified linear depiction; it did not match the `docs/common ground/index.html` "Proposed — top orchestrator + coverage" graph. Rebuilt `PipelineDiagram` to mirror it exactly: vertical **Query planner → Hybrid retrieval ×N (→ RRF) → Density → Author diversity → Coverage check → …**, plus a dashed **coverage → retrieval re-query loop-back edge** ("re-query (cap 1)") routed up the left margin. `tutorPipeline.ts` edges + `retrieval` relabel; 17 frontend tests + tsc green; verified in-browser against the reference graph.

## 2026-05-21 — Top orchestrator (query planner) + coverage check (Option 2)

Problem: "What is the bias-variance tradeoff?" pulled loosely-related chunks and the draft gave the bias formula but not the variance formula. Two causes (retrieval coverage + synthesis asymmetry); both addressed.

- **Query planner = top orchestrator** — `extract_concepts_ex` now returns a `QueryPlan{concepts, suggested_authors, queries, facets}` from its one nano call (`EXTRACT_CONCEPTS_BUDGET_PROMPT` extended). `queries[]` = targeted retrieval strings; `facets[]` = what the answer must cover. Caller + test fixtures updated.
- **Multi-query retrieval + RRF** — `_multi_query_candidates` fans the planned queries out in parallel and `_rrf_merge` (reciprocal-rank fusion, keyed by `chunkId`) fuses them with the raw-query anchor pool. Env `TUTOR_MULTI_QUERY` (default 1).
- **Coverage check (CRAG-lite)** — new `agents/coverage.py`: `assess_coverage(facets, sources)` (nano) grades which facets the selected sources miss; `fill_missing_facets` re-queries them (cap 1) and re-ranks. Env `TUTOR_COVERAGE_CHECK` (default 1). Best-effort (errors → proceed). This is what ensures both the bias AND variance formula get retrieved.
- **Synthesis nudge** — `formal_statement` spec: "if the concept decomposes into named components, give the formula for EACH."
- Frontend: `Concept extraction` node relabelled **Query planner**; new locked **Coverage check** node ("facet re-query") between Author-diversity and Figure-judge.
- Tests: `test_query_planner_coverage.py` (8); fixtures updated. Full backend suite + tsc + 34 vitest green. Verified in-browser: bias-variance query → 8 sources (was 4), formal statement shows the MSE decomposition with both bias and variance terms, 0 service errors.

## 2026-05-21 — About-model modal: Apply button + auto-open on Tutor select

- **Staged edits + Apply.** `AboutModelModal` now holds a local draft (`{stageModels, diversityAuthors, tutorWorkflow}`) seeded from the applied config on open; pipeline-node edits change the draft, not live state. A pinned footer shows "Unsaved pipeline changes" and an **Apply** (commits via new `onApply` prop → App setters, then closes) / **Cancel** (discards). Contract change: AboutModelModal lost the three live `onChange` props, gained `onApply(PipelineConfig)`.
- **Auto-open.** Selecting **Tutor** in the ModePicker now also calls `onAbout()` → opens the modal (the (i) button still works). `ModePicker.tsx`.
- CSS: `.about-model__footer` + `.about-model__btn` (neon theme). Tests updated; tsc + 31 vitest green. Verified in browser: edit→Apply→reopen persists; Tutor select opens modal.

## 2026-05-21 — Planner was silently failing (strict-output bug) — fixed + slimmed

Audit (triggered by "the modal looks the same") surfaced two things via service-log monitoring:
1. **Modal "same" = runtime, not code**: two dev vite servers (:5175 + :5176) from repeated `dev.sh` runs + an un-reloaded tab. Cleaned to one server + hard reload → modal correctly shows **Planner** (no Critique). Disk had been correct all along.
2. **Real bug: `build_synthesis_plan` 400'd every run** — `SynthesisPlan.outline: dict[str,str]` is invalid for OpenAI strict structured outputs (open-keyed object). It failed *gracefully* (→ None), so the Planner never produced a plan and the orchestrator silently used the per-author fallback, not LLM-chosen tasks. After fixing the dict it then hit `LengthFinishReasonError` (850-token cap truncation).
   - Fix: slimmed `SynthesisPlan` to exactly **`{thesis, contrasts, tasks}`** (dropped the carried-over `outline`+`ledger`; removed `OutlineItem`/`LedgerClaim`), trimmed `SYNTHESIS_PLAN_PROMPT`, raised the cap to 1200. **Proven against the live API** (4-source case: thesis + 2 contrasts + 4 LLM-chosen tasks) and in-app (0 planner failures, 0 errors).
   - Regression guard added: `test_structured_output_models_are_openai_strict_safe` fails if any `response_format` model gains an open-keyed dict.
- Full chat suite + frontend tsc/vitest green.

## 2026-05-21 — DAG re-evaluation: merge Planner+Orchestrator, drop Critique node

Critical re-eval of the full pipeline (documented in `docs/common ground/index.html` §6).

- **Merged Synthesis-plan + Orchestrator into one Planner agent.** `SynthesisPlan` gained `tasks: list[WorkerTask]`; `SYNTHESIS_PLAN_PROMPT` now also emits the worker decomposition. `run_orchestrator_workers` reads `plan.tasks` (per-author `_fallback_tasks` when empty) — the standalone `orchestrate()` call + `ORCHESTRATOR_PROMPT` path are gone. **One planning LLM call instead of two**, no plan-vs-orchestrator drift. Frontend: the `plan` node relabelled **Planner**.
- **Dropped the Critique node** from the canonical diagram (`tutorPipeline.ts` + `PipelineDiagram` layout/edges → `draft → vision_explain`). The critique code stays **opt-in** via `TUTOR_DEEP_CRITIQUE=1`; it's just off the standing graph.
- Why: the plan's `contrasts` and the orchestrator's `tasks` were the same post-retrieval decomposition computed twice; Critique is off by default and rarely fires. Figure-judge / Vision-explain kept separate (preserve caption-first cost optimization).
- Tests: orchestrator tests updated (planner-tasks drive workers; `test_orchestrator_uses_planner_tasks`); PipelineDiagram tests assert Planner present + Critique absent. 70 backend + 12 frontend green; tsc clean. Verified in browser: modal shows Planner, no Critique (Draft → Vision explain).

## 2026-05-21 — Orchestrator-workers: real LLM orchestrator + workflow-aware diagram

Closed the two gaps from the audit in `demo.md` / `docs/common ground/`:
1. The "orchestrator" was a fixed `group_sources_by_author` code rule (= parallelization, not orchestration).
2. The modal pipeline diagram never redrew — it showed the same single "Draft / synthesis" box regardless of workflow.

- **Real orchestrator LLM** (`orchestrator_workers.orchestrate`): `ORCHESTRATOR_PROMPT` → `OrchestratorPlan{tasks:[WorkerTask{focus, source_ranks}]}`. The LLM decides, per question, how many workers and each one's focus (per author, per sub-topic, or merged). `run_orchestrator_workers` maps each task's ranks → sources → parallel workers → streaming synthesizer. **Falls back** to the per-author split (`_fallback_tasks`) when the orchestrator declines/fails, and to the single draft when <2 subtasks. New `WorkerTask`/`OrchestratorPlan` schemas.
- **Workflow-aware diagram**: `PipelineDiagram` derives `effectiveNodes/Edges/Layout` from `tutorWorkflow`. In `orchestrator` mode it drops the `draft` node and splices in `Orchestrator → Worker ×3 (parallel, dashed delegate edges) → Synthesizer`, shifting the tail down. Single mode unchanged. The orchestrator node carries the draft model dropdown.
- Tests: `test_orchestrator_workers.py` now covers `orchestrate` graceful failure, `_fallback_tasks`, fallback paths, and that LLM-chosen foci drive the workers (`test_orchestrator_uses_llm_tasks`). PipelineDiagram tests assert the orchestrator/single render difference. Backend + frontend green.
- Verified in browser: switching the **Drafting workflow** node to Orchestrator visibly morphs the diagram into Orchestrator→Workers→Synthesizer — the modal now matches the canonical pattern in `docs/common ground/index.html`.

## 2026-05-21 — Orchestrator-workers drafting workflow (per author)

The "Synthesis plan" step was plan-and-write, not the orchestrator-workers pattern (Anthropic: orchestrator decomposes → parallel worker LLMs → synthesizer integrates). Added a true orchestrator-workers workflow, split per author, as a **selectable** drafting workflow (default stays single-draft).

- New `src/services/chat/agents/orchestrator_workers.py`: `_group_sources_by_author` (reuses `diversity.author_key`), `run_author_worker` (one structured `AuthorBrief` per author, grounded only in that author's sources), `run_orchestrator_workers` (groups → `asyncio.gather` workers → streams the synthesizer). Returns `(None, {})` to signal fallback (<2 authors or all workers fail).
- `AuthorBrief` schema (`output.py`); `ChatRequest.tutorWorkflow: "single"|"orchestrator"|None`.
- Prompts: `AUTHOR_WORKER_PROMPT` (worker), `SYNTHESIZER_ADDENDUM` (appended to `DEEP_TUTOR_INSTRUCTIONS` — integrate briefs into one throughline, compare authors, bundle stays citation truth).
- `deep_tutor`: refactored the OpenAI structured-stream loop out of `_stream_draft` into a shared `_stream_structured(messages, model, on_aspect_delta)` reused by both the single draft and the synthesizer. `_resolve_workflow`; `run_deep_tutor` branches via `_draft_coro` (orchestrator with graceful fallback to `_stream_draft`). Workers default to nano (`TUTOR_WORKER_MODEL`); synthesizer = Draft-node model. `TUTOR_WORKFLOW` env default.
- Frontend: **Drafting workflow** node (Single draft / Orchestrator (per author)) between Synthesis plan and Draft; `NodeChoiceDropdown` `ChoiceValue` widened to allow strings; `tutorWorkflow` plumbed App→chat.ts→body.
- Tests: `test_orchestrator_workers.py` (8); 95 related backend tests + frontend tsc/vitest green.
- Verified in browser: orchestrator on "compare regularization across authors" produced a Definition with one separately-attributed bullet per author (Goodfellow norm penalty / Atwan Lasso-Ridge-ElasticNet / Peters learning theory / Murphy empirical risk), synthesized under one throughline; SSE still streamed; ~45s vs ~20s single-draft.

## 2026-05-21 — Synthesis plan + evidence ledger (coherent, multi-author answers)

Problem: the 7 tutor aspect fields read as disjoint pieces — one draft call improvised each field from raw chunks, with no shared thesis and no deliberate author comparison. Workflow option A: a plan step before the draft.

- New `SynthesisPlan` schema (`schemas/output.py`): `thesis`, per-aspect `outline`, an `ledger` of author-tagged source-ranked `LedgerClaim`s, and explicit `AuthorContrast`s.
- `build_synthesis_plan(query, sources, model)` in `deep_tutor.py` — one structured `.parse` call (`SYNTHESIS_PLAN_PROMPT`); graceful `None` on failure. Runs **parallel with the figure-judge** (`plan_task` started post-density, awaited before the draft) so added wall-clock ≈ max(plan, judge).
- `_build_user_message` injects `<synthesis_plan>`/`<evidence_ledger>`/`<contrasts>` blocks; `DEEP_TUTOR_INSTRUCTIONS` gained a `<plan>` section: follow the thesis as the spine, draw facts from the ledger (consistency across fields), cross-reference aspects, and surface each contrast explicitly ("X frames it as … [n], whereas Y …[m]").
- Toggle+model in one control: pipeline node **Synthesis plan** (between Figure-judge and Draft) whose dropdown = **Off (single-draft)** + chat models. `stageModels.plan`: `"off"` disables; a model id enables. `_resolve_plan_model` + env `TUTOR_SYNTHESIS_PLAN` (default 1). No new request field — rides `stageModels`. `NodeModelDropdown` gained `leadingOptions` for the "Off" entry.
- Tests: `test_synthesis_plan.py` (10), plus updated `_patch_pipeline`/stage-model fixtures to mock `extract_concepts_ex` + `build_synthesis_plan` (these were also needed by the prior auto-diversity change). 88 related backend tests + frontend tsc/vitest green.
- Verified in browser: comparative query now opens with a thesis + explicit Goodfellow-vs-Atwan contrast across 4 authors; node dropdown shows Off + models.

## 2026-05-21 — Adaptive author count ("Auto" via the concept model)

Follow-up to the diversity step: the author count is no longer a fixed user setting — it's a **cap with an Auto mode** that adapts per question.

- Effective target = `min(cap, model_suggestion, authors_available_in_pool)`. The availability clamp (round-robin saturation) means a single-author topic always yields one author, regardless of the setting.
- The model suggestion folds into the **concept-extraction** call (no extra LLM call): `extract_concepts_ex()` + `EXTRACT_CONCEPTS_BUDGET_PROMPT` return `{concepts, perspectives}`; `perspectives` (1..cap) reflects how comparative/broad the *question* is. The reasoning model = whatever is selected for the Concept-extraction node.
- `deep_tutor._resolve_diversity(req_val) -> (mode, cap)`: `off` / `fixed` / `auto`. Auto is the default when `TUTOR_DIVERSITY=1`. Env: `TUTOR_DIVERSITY_MAX_AUTHORS` (4), `TUTOR_DIVERSITY_DEFAULT` (`auto`).
- Request field widened: `diversityAuthors: int | "auto" | None`.
- Frontend: Author-diversity dropdown gains an **Auto** option (`Off / Auto / 2 / 3 / 4`), default Auto; `ChoiceValue = number | "auto"` threaded through `NodeChoiceDropdown` → `App` → `chat.ts`.
- Diversity is additive, not subtractive: it never suppresses naturally-relevant diverse sources, only stops *padding* spread beyond the target.
- Tests: +4 resolver cases (27 total in `test_diversity.py`); backend import + frontend tsc green; in-browser Auto query ran clean.

## 2026-05-21 — Author-perspective diversity in tutor retrieval

Problem: tutor answers often drew all sources from one author/book, hiding alternative explanations. Added an author-diversity selection step (facet = author primary, year tiebreak).

- New module `src/services/chat/retrievers/diversity.py`: `author_key()` (normalized `authors_short` > `authors` > `book`), `diversify_section_keys()` — round-robin across distinct author groups so the selection spans up to N authors before taking a 2nd section from any one; year-spread tiebreak on extra picks. Pure + unit-tested (23 cases).
- `deep_tutor._density_select` takes `target_authors`; when ≥2 it diversifies `final_keys` (Plan A) and then does a **stratified fill** (Plan B) — pulls best sections for under-represented authors from the already-fetched wide candidate pool (no extra Qdrant calls in v1). `run_deep_tutor` resolves the target: `req.diversityAuthors` else `TUTOR_DIVERSITY_TARGET_AUTHORS` (default 3) when `TUTOR_DIVERSITY=1`, else 0 (off).
- Request: `ChatRequest.diversityAuthors: int|None` (0/1 = off, N≥2 = target).
- Frontend: new **Author diversity** node in the About-model pipeline diagram (between Density-select and Figure-judge) with a `NodeChoiceDropdown` (Off / 2 / 3 / 4 authors, `SET` badge), wired through `App.diversityAuthors` → `chat.ts` request body. Pipeline graph re-laid-out + edges updated.
- Verified: 23 backend + frontend tsc green; in-browser the bias-variance query went from murphy-dominated to **3 distinct authors** (mackay, goodfellow, murphy).
- **Known limitation / next step:** Plan B fills from the wide pool only, so a genuinely single-author pool stays single-author. True stratified retrieval = map under-covered authors → their `book_slug`s (via `books.list_books`) → run `hybrid_search(book_slugs=...)` to pull their best sections from Qdrant. Recommended follow-up; uses the existing book-slug payload filter.

## 2026-05-21 — Vision-explain model is now user-selectable

- The figure **Vision explain** stage is now an overridable pipeline node (was locked). In the About-model modal it has a SWAP dropdown like the other LLM stages.
- Frontend: `web/src/data/tutorPipeline.ts` — added `"vision_explain"` to `StageKey`; node `vision_explain` set `stage:"vision_explain"`, `locked:false`. `PipelineDiagram`/`NodeModelDropdown` need no change (any non-locked node with a stage renders a picker).
- Backend (`deep_tutor.py`): new `_resolve_vision_model(stage_models)` — honors `stageModels["vision_explain"]` when it is a known chat model, else the vision default (`TUTOR_DEEP_VISION_MODEL` or `gpt-4o-mini`). Note: the default base is the **vision** model, not nano (text stages default to nano). `m_vision` is threaded through `build_vision_explanations(..., model=)` → `_explain_figure_vision(..., model=)`. A non-vision pick degrades gracefully (falls back to caption on API error).
- `stageModels` is a free-form `dict[str,str]` in the request schema, so no schema change. Verified: backend import + `test_stage_models.py` pass; `tsc --noEmit` clean; dropdown selectable + flips upward in browser.

## 2026-05-20 — Tutor limitation fixes: inline LaTeX, figure explanations, modal dropdown

Three user-reported tutor limitations, each verified in-browser on the dev stack (:5175 → backend :8766).

### 1. Inline LaTeX rendered as raw red text

- Root cause: the LLM emits **malformed/mixed math delimiters**, not clean `\(…\)`. Real shapes found in stored answers: `\$( \hat{\theta} \)$` (stray `$` glued to both delimiters) and `\($p(D\mid\theta)$\)` (`$…$` nested inside `\(…\)`). KaTeX (`throwOnError:false`) renders the garbage as red source text. Clean `$$…$$` always worked, which masked the issue.
- Fix (frontend, model-output-independent): new `normalizeMathDelimiters()` in `web/src/components/views/TutorView.tsx` — single-pass state machine that rewrites `\$(`→`\(`, `\$)`/`\)$`→`\)` (consumes the stray `$` on the closer), and strips bare `$` *inside* an open `\(…\)`/`\[…\]` span. Applied at the entry of `renderInlineWithCites`.
- `MessageThread.tsx` `parseInline` now also normalizes and handles inline `\(…\)` and single-line `\[…\]` (previously `$…$`-only), so non-Tutor modes render inline LaTeX too.
- `Math.tsx`: KaTeX `errorColor` set to muted grey (`#888`) so any future parse failure is less jarring than bright red.
- Tests: `web/src/components/views/normalizeMathDelimiters.test.ts` (13 cases incl. both real malformed shapes + clean pass-through). `npm run test` + `tsc --noEmit` green.

### 2. Figures shown without a real explanation

- Root cause: `TUTOR_DEEP_VISION_EXPLAIN` defaulted to `"0"` in `deep_tutor.py`, so `build_vision_explanations()` returned `{}` and figures fell back to the OCR caption + short judge_reason (generic, not tied to what the figure shows).
- Fix: default flipped to `"1"` (env-overridable). Explicitly set `TUTOR_DEEP_VISION_EXPLAIN=1` in `ops/docker/docker-compose.yml` (chat svc) and exported in `scripts/dev.sh`. `_VISION_EXPLAIN_PROMPT` rewritten to make the vision model (gpt-4o-mini) name axes/curves/trends, tie them to the concept, and avoid invented numbers.
- Cost: ≤ 3 extra vision calls per tutor turn (capped at the image-judge's 3 approved figures), fired in parallel, `max_completion_tokens=220`; zero when no figures. Graceful fallback to caption+reason on any error. **Backend restart required** to pick up the new default.

### 3. Model dropdown clipped inside the About-model (Tutor mode) modal

- Root cause: `NodeModelDropdown` portal opened downward only; for low pipeline stages the option list was clipped at the viewport/modal bottom, hiding providers (e.g. DeepSeek).
- Fix (`web/src/components/NodeModelDropdown.tsx` + `.node-dd__panel` in `app.css`): measure space above/below the trigger, **flip upward** when space below is insufficient, and clamp `max-height` to available space (≤320px) with internal `overflow-y:auto`. Reposition recompute wrapped in `requestAnimationFrame` to avoid stale rects during modal-body scroll.

## 2026-05-19 — Image library expansion + tutor UX hardening

Big session. Three workstreams.

### Workstream A — image collections, 1 → 25 books

- Before: only `introduction_images` (271 pts, ISLP only). Tutor queries over any non-ISLP book returned zero figures, silently.
- After: all 6 `<field>_images` collections live. 25 books indexed. 8083 total image points (30× growth).
- New module `src/ingestion/ingest_images_only.py`. Image-only ingest path that does NOT touch the text collection. Auto-detects markdown format:
  - `vlm` format (new VLM output): `![](images/<sha>.jpg)` refs + `<details><summary>` captions.
  - `epub` format (legacy EPUB-to-md): `![alt](markdown/<title>/media/…/*.jpg)` refs + italicised follow-line captions; filters `Art_P*.jpg` inline-math glyphs.
  - Caption builder pulls preceding prose context when raw caption is empty.
- `_persist_images` in `src/ingestion/pipeline.py` now upserts in batches of 100 (was single-shot, which timed out on `peck` 657-image book).
- Path resolution: symlink `src/ingestion/processed/markdown -> /home/iohan/Downloads/EPUB/markdown` so EPUB image refs resolve via the existing `book_dir / img_path` fallback in `_make_image`.
- Preflight tool `ops/scripts/preflight_image_ingest.py` — read-only audit of slug → vlm/epub-md path + on-disk image count vs current Qdrant size. Writes `data/parsed/_ingest_audit.json`.
- Manifest entries registered with synthetic `chapter_id="images_only"`, `chunk_count=0`, `image_count=N` so `--status` / `rag-verify` see image-only runs.
- `render_state.py` now queries Qdrant directly for live image counts (manifest fallback was zero because image-only flow predates registration logic).
- 116 legacy `image_reference = "(no caption found)"` points pruned from `introduction_images` (orphan ISLP-format records).
- Library docs (`docs/library/<collection>.md`) refreshed; new `spark_ts` row added to econometrics.

### Workstream B — figure rendering inside tutor answer

- Backend `_convert_to_tutor_answer` (deep_tutor.py):
  - Injects each approved figure into the relevant aspect markdown as `lead → ![cap](url) → explanation`. Lead uses role-aware varied templates (`_LEAD_TEMPLATES` per role + `_LEAD_GENERIC` + `_LEAD_NO_TOPIC`). Role `"other"` normalised → `"figure"` so prose never reads `"The other below from …"`.
  - Aspect placement is overlap-scored: figure caption + judge_reason vs each aspect body's token set. TL;DR excluded from auto-placement (kept concise). Falls back to `aspect_hint` then `examples`.
- SSE: `figures_full` event now always emitted (was guarded behind `if approved_figures`). New companion `figures_meta` event carries `{status, reason, candidateCount, approvedCount}` so the UI can surface `no_candidates` / `all_rejected` / `error` instead of failing silently. Frontend currently logs via `console.warn`.

### Workstream C — TutorView rendering + tutor LaTeX

- `web/src/components/views/TutorView.tsx`:
  - New `Block` kinds: `image`, `list`. Renders `![](url)` as `<figure>` + lazy `<img>`; bullet/numbered lists parsed and rendered.
  - `[F<n>]` / `[Figure <n>]` / `[Image #<n>]` variants tokenised as figure pills (`href="#fig-N"`). `<figure>` elements receive sequential `id="fig-N"`. Hashchange auto-opens every collapsed section and scroll-anchors.
  - Bare-LaTeX auto-wrap: backslash command (whitelisted via `LATEX_COMMANDS` Set, includes Greek letters, `mathbb`/`hat`/`vec`, `frac`/`sum`/`int`, `big`/`Big` delimiters, etc.) gets wrapped in inline math even when the LLM forgot `$..$`. Whitelist prevents misfires on literal backslash prose.
  - LaTeX-style `\( … \)` inline and `\[ … \]` block delimiters now parsed alongside `$..$`/`$$..$$`.
  - Lead with TL;DR open by default; chevron rotates 0° → 90° on toggle; section body uses `max-height + opacity` transition (220ms ease-out enter, ease-in exit per ui-ux-pro-max review). `prefers-reduced-motion` honoured.
- Backend latex-escape repair in `deep_tutor.py`:
  - `_repair_latex_escapes` pre-pass before every `json.loads(raw)` — doubles single backslashes preceding ~80 whitelisted command names (negative lookbehind, doesn't double-escape).
  - `_repair_latex_post` post-pass on streamed-parse path — reattaches `\` to TAB/NL/BS/FF/CR control chars that JSON already collapsed onto known latex stems (e.g. TAB+`heta` → `\theta`). Word-boundary check avoids false positives on prose.
  - `_wrap_bare_math` paragraph-level wrapper — bundles contiguous math token runs in `$..$` so KaTeX activates. Skips runs without any `\command`.
  - Prompt strengthened with JSON-escape rule and `$..$` wrap requirement in `prompts/deep_tutor.py`.

### Other fixes folded into this session

- Sidebar "new conversation never saved" — actually saved but `convGroups` never updated post-create. `App.tsx::handleSend` now prepends digest to `convGroups.today`.
- `book_filter: null` → 422 on `POST /api/conversations`. Schema relaxed to `list[str] | str | None`, coerce null/empty → `"ALL"`.

### Tests + verification

- Backend: 45/45 pytest pass (was 21; +24 for latex repair, figure injection, aspect scoring, lead templates, math wrapping).
- Frontend: `tsc --noEmit` clean.
- Image judge quality eval (`pytest -m quality_images`, 32-row labelled set): precision 0.952, recall 0.909, F1 0.930, placement_soft 1.000, median latency 1804 ms — no regression vs pre-ingest baseline.
- Live verification per field: heteroskedasticity (econ), prob-density (math), CNN (ml_dp), VaR (risk), propensity matching (causal), CLT (intro) — all return ≥ 1 figure.
- Qdrant snapshot taken post-ingest (12 collections, ~30s).

### Knobs / files of note

- `src/ingestion/ingest_images_only.py` — image-only ingest entry point.
- `src/ingestion/pipeline.py:_persist_images` — chunked upsert (BATCH=100).
- `src/services/chat/agents/deep_tutor.py` — `_repair_latex_escapes`, `_repair_latex_post`, `_wrap_bare_math`, `_choose_target_aspect`, `_build_lead`, figure injection in `_convert_to_tutor_answer`.
- `web/src/components/views/TutorView.tsx` — Block parser extensions, figure pills, math wrap, auto-expand, animation.
- `docs/tasks/ingestion.md` — "Image-only ingest" section.

## 2026-05-18 — Tutor view layout (#38)

- Paragraphs in `TutorView` are now `text-align: justify` with `hyphens: auto`.
- `## H2` section titles centered; each section is collapsible (button + rotating `›` chevron, default open). State held as `Set<number>` of closed section indices in `TutorView`.
- `Math.tsx` no longer renders the `<span class="math-block__tag">MATH</span>`; the `.math-block::before { content: "math" }` badge was also dropped. `.math-block` + `.katex-display` use `text-align: center` so the formula sits centered.
- Verified in browser via the chrome MCP on `localhost:5175`. See `docs/services/chat-features/38-tutor-layout.md`.

## 2026-05-18 — Conversation load fix (#37)

- Bug: clicking an old conversation in the sidebar appeared to start a new one. Two causes.
- (A) `App.tsx::handleSend` called `setConversationId(conv.id)` then `sendMessage(text)`. `sendMessage`'s closure captured the old `state.conversationId` (`null`), so the SSE request body shipped `conversationId: null` and `chat_event_gen` in `src/services/chat/api.py` skipped `store.append_message(...)`. Every conversation row was persisted, but no message rows ever were. Fix: `sendMessage(text, convIdOverride?)` accepts an explicit id; `handleSend` passes the freshly-created `conv.id`.
- (B) `activeConvTitle` looked for `.active` on conv items (never set), so the topbar always read `New conversation`. Fix: look up the title by `conversationId` across every date group.
- UX: `MessageThread` now distinguishes "no conversation loaded" (welcome) from "conversation loaded but empty" (`No messages in this conversation yet.`). Avoids the same "looks-like-a-new-chat" confusion for legacy orphan rows.
- Verified in-browser via the chrome MCP: topbar updates, sidebar highlight moves, empty-state copy switches. See `docs/services/chat-features/37-conv-load-fix.md`.

## 2026-05-18 — Tutor view restyle (#36)

- `TutorView` recolored: hardcoded `#38bdf8` (sky blue) fallbacks in `web/src/styles/tutor.css` replaced with red `#E5484D` (titles, citation pills, sources title, source numbers, math border).
- Sources panel inside `TutorAnswer` is now a click-to-expand toggle. Default collapsed; count shown next to the label; rotating `›` chevron.
- `Thinking…` indicator restyled to Claude-Code-style: italic muted mono label + 3-dot ticking ellipsis (`msg__thinking` in `app.css`), replacing the old red dot-bounce pill (`msg__pending--motion` rule retained but unused at the thinking site).
- Scope kept narrow: only `.tutor-view__*` + the thinking indicator. Theme tokens (light navy, dark red) untouched. See `docs/services/chat-features/36-tutor-restyle.md`.

## 2026-05-18 — Chat usage telemetry + figure-serving route + streaming phase + conversation hydration

**Backend**
- New SSE event `usage` emitted at end of every `/api/chat` stream in `src/services/chat/router.py` (both v1 and v2 paths). Fields: `durationMs`, `promptChars`, `completionChars`, `estTokens`. `estTokens = (promptChars + completionChars) // 4` — char-based heuristic, NOT a real model usage count.
- New route `GET /api/figures` in `src/services/chat/api.py::serve_figure`. Serves whitelisted image files for figure previews. Whitelist roots: `/home/iohan/Documents/Books` and the repo's `data/` dir. Validates extension (png/jpg/jpeg/gif/webp/svg). Rejects traversal via `Path.resolve(strict=True)` + prefix check against the whitelist roots.
- `retrieval.py` builds chart URLs via new `_chart_url` helper as `/api/figures?path=<urlencoded image_path>`.

**Frontend**
- New `streamingPhase: "idle" | "thinking" | "writing"` field in `ChatState`. Flips to `writing` on first `token` event; back to `idle` on `done`. Drives the topbar stats pill plus thinking/caret animations.
- Reducer captures the new `usage` event into `ChatState.usage`.
- New reducer action `LOAD_CONVERSATION`: resets state to a hydrated conversation when user clicks a sidebar item. Wired to `GET /api/conversations/{id}`. New `loadConversation(id, messages)` exposed from `useChat`.

## 2026-05-18 — Full Docker stack + UI overhaul + snapshot routine

**Infra**
- `ops/docker/docker-compose.yml` now bundles **4 services**: `qdrant`, `statrag-chat` (Dockerfile.chat), `statrag-web` (Dockerfile.web → nginx serving Vite build + `/api` proxy), `qdrant-backup` (oneshot `curlimages/curl` running `ops/scripts/qdrant_snapshot.sh`).
- Snapshot routine: runs on every `up`, snapshots every collection via Qdrant API, persists to host-mounted `data/qdrant_snapshots/`, prunes to `SNAPSHOT_KEEP=3`.
- New volume mount: `/qdrant/snapshots` (snapshots are NOT under `/qdrant/storage` — separate mount required).
- Manual safety tarball: `data/qdrant_backups/manual_<ts>.tgz`.

**UI**
- Palette: dark = pure black (`#000`) bg + red accents (`#E5484D`) + red-tinted borders; light = cream paper + cobalt navy. Both themes synced across `tokens.css` + `neon.css` + `tweaks.ts` + `App.tsx` defaults.
- Typography: serif `Crimson Pro`, body `Atkinson Hyperlegible`, mono `JetBrains Mono`. Old `IBM Plex` family removed from preload.
- BookModal v2: removed 5-KPI header → single "Library" tile; collection filter chips (`field`-grouped) with bulk-toggle (right-click); standardized horizontal card pattern (140px cover + body grid); real PDF first pages extracted via `pdftoppm` into `web/public/covers/<slug>.jpg` (17 of 26 books — fallback SVG for the rest). Origin PDFs preferred over OCR `_layout.pdf` reconstructions.
- ModelPicker v2: provider-grouped collapsible (OpenAI / DeepSeek), inline SVG provider icons in both trigger button and group tiles.
- Polish layer in `app.css`: focus-visible rings, tabular-nums, press scale, smooth transitions, fancy themed scrollbars (slim 10px global + 12px modal-body with accent thumb).
- Welcome hero centered (vertical + horizontal in main area).
- Input bar: line-height-aware grow up to 10 lines then auto-overflow scroll.
- Topbar: removed Settings button + status dot.

**Docs**
- `docs/services/chat.md` Quick start now lists Option A (full Docker) vs Option B (host dev).
- `ops/docker/README.md` reflects 4-service compose + backup routine.

## 2026-05-17 — Chat service (Part 2) v1

Adds `src/services/chat/` + React+Vite+TS SPA at `web/`. Conversational layer over the existing retrieval backbone. Chinese-wall compliant.

- Backend: FastAPI app at `src/services/chat/api.py`. Routes: `/api/{health,books,books/{slug},search,models,conversations,conversations/{id},preferences,chat}`.
- `/api/chat` is SSE (sse-starlette) emitting `meta` → `token`/`paragraph_break`/`math_block`/`figure`/`source_chip` → `sources_full` → `figures_full` → `retrieval_meta` → `done` (or `error` + `done`).
- Hybrid retriever fans out across per-field text collections grouped by requested book slugs, RRF-fuses dense (text-embedding-3-large) + sparse (Qdrant/bm25 via fastembed), then globally re-sorts by score.
- Sentence-level highlight reranker (`highlights.py`) provides character ranges for `SourceModal`. Heuristic path per design 05_rag_pipeline.md.
- LLM router (`llm/router.py`) supports OpenAI + DeepSeek via the `openai` SDK (DeepSeek through `base_url`). Routing by `model_id` prefix.
- Conversation persistence: SQLite at `data/chat.db` (WAL, lazy init). Tables: conversations, messages, prefs.
- Frontend: React 18 + Vite + TS. Ports the design at `docs/upgrades/Demo/ChatSystem/` 1:1 (tokens, glass surfaces, neon dark + financial light themes). KaTeX for math. Custom SSE client over `fetch + ReadableStream` to support POST body.
- Tests: 61 pytest cases under `src/services/chat/tests/` covering books, retrieval, highlights, LLM router, store, orchestrator + FastAPI health.
- Reference design preserved under `docs/upgrades/Demo/ChatSystem/`.

Run: `./scripts/dev.sh` (backend `:8765` — 8000 taken by another docker app — + Vite `:5173`). Frontend deps: `npm install` once in `web/`. Ops doc: `docs/services/chat.md`.

### 2026-05-17 (later) — Phase 0 fixes: chat works end-to-end in browser

- Payload mapping: `retrieval._point_to_source` now reads `h1`/`h2_path`/`page_from` (actual ingestion payload schema) instead of nonexistent `section_path`/`section_title`. Section label = last `" | "` segment of `h2_path`; title = full `h2_path`.
- Emit `source_chip` events: orchestrator now emits one `source_chip` per source before `sources_full`, so inline chip blocks render under the answer.
- Conversation persistence: `App.handleSend` lazily creates a conversation via `POST /api/conversations` on the first send and threads `conversationId` into subsequent `/api/chat` calls.
- Status dot: 10s `/api/health` poll wired to `Topbar.online`.
- Source chip → SourceModal lookup: matches `${chapter} ${section}` joined form OR plain section, with `endsWith` fallback.
- Figure search: pre-flight against `client().get_collections()` to skip nonexistent `<field>_images` collections — avoids 5x 404 spam.
- SSE parser: handles both `\r\n\r\n` (sse-starlette default) and `\n\n` frame delimiters. Frames split on `/\r?\n/`.

**Important build cleanup**: `tsc -b` (from `npm run build`) was emitting `.js` artifacts next to every `.tsx` source. Vite resolved `import "./App"` to the stale `App.js` instead of the live `App.tsx`, masking all edits. Fix: deleted all `web/src/**/*.js` artifacts, set `"noEmit": true` in `web/tsconfig.json`, and changed the build script to `tsc -b --noEmit && vite build`.

**Verified in browser** (Chrome via MCP):
- User message renders, assistant streams tokens, paragraph breaks honored.
- TUTOR MODE badge populated (books, source count, latency).
- Inline `**Book (...)**` bold rendered in serif.
- 5 inline source chips clickable.
- ContextPanel populates 5 SOURCES (with rank, score badges, excerpt) + 2 FIGURES.
- Status dot turns green via `/api/health` poll.

**Next step**: make chat work end-to-end in the browser. Backend SSE verified via curl (Ridge query → 5 sources + math block + tokens). UI compiled clean. Next pass = open `http://localhost:5173`, send a tutor query, fix whatever breaks (paragraph_break boundaries, KaTeX rendering, source chip wiring, ContextPanel population, BookModal toggles, model picker switch). See "Next step" in `docs/services/chat.md`.

## 2026-05-15 — `theme` payload field

Added `theme` field (string) to text and image collections + `BookMetadata` schema + yaml.

- `ingestion/books/<slug>.yaml` gains a `theme:` key (free-form).
- `pipeline.load_book_static_metadata` reads it; `_flat_meta` and `_persist_images` write it into payload.
- Existing ISLP (502 text + 201 image) backfilled via `set_payload`+`FilterSelector` to `theme="Machine Learning"`.
- Existing Hansen (358 text + 70 image) backfilled to `theme="Probability and Statistics"`.
- Image `book` alias also added during backfill so filter-by-`book` works on both collections uniformly.

## 2026-05-15 — Numeric-aware hierarchy + pipe separator (steps 40-41)

`h2_path` now uses ` | ` (PATH_SEP) between hierarchy levels and is built from a numeric-aware stack:

- Headers with numeric prefix (`2.1`, `2.1.1`) form the **backbone**. Push pops deeper-or-equal entries from the stack first, so `2.1.2` correctly replaces a previous `2.1.1` subtree.
- Headers WITHOUT a numeric prefix (e.g. `Prediction`, `Inference`, `K-Nearest Neighbors`) are appended as **leaf subsections** of the last numbered ancestor — they accumulate into `unnumbered_tail` until a new numbered header arrives, which clears them.
- `RE_OCR_HEADER_NOISE` filters obvious Python REPL output (`Out[N]:`, `In[N]:`, `>>> `, `... `) and code comments (`fit a model ...`) that the source markdown spuriously rendered as headers. They are kept in section body, not promoted to path.
- `section_id` derives from `h2_path` with PATH_SEP replaced by `__` and other chars sanitised. Hierarchy is recoverable from the id.

Example produced for ISLP ch02:
```
2.1 What Is Statistical Learning? | 2.1.1 Why Estimatef? | Prediction | Inference
2.2 Assessing Model Accuracy | 2.2.3 The Classification Setting | The Bayes Classifier | K-Nearest Neighbors
2.4 Exercises | Conceptual | 3. We now revisit the bias-variance decomposition | Applied
```

Effects on ch02 chunk count: 48 → 32. OCR-noise headers no longer create empty/spurious sections.

Invariants 9 + 10 added to `invariants.md`.

## 2026-05-15 — `book` field alias

Added `book` payload field as an alias for `book_slug`. Convenience for short-name filters (`Filter(must=[FieldCondition(key="book", match=MatchValue(value="islp"))])`).

## 2026-05-15 — Architecture redesign (steps 32-38)

After diagnostics flagged 4 issues — `book_slug` confused with display name, `page_from=-1` leaks, chunks were 800-char children (not section-level), `h1` empty when no `#` header — the chunking and metadata pipeline were rewritten:

- **Single-tier chunking**: 1 section = 1 chunk; split at 8000 tokens via tiktoken `cl100k_base`. Parent-Doc pattern removed. `retrievers.py` returns Qdrant points directly.
- **Separate `book_name` / `authors`** added to payload (distinct from `book_slug`).
- **`regex_pass.parse_chapter`** rewritten as line-streaming with running `current_page`. `_peek_page_before` seeds page from prelude before `line_start`.
- **`h1` fallback**: defaults to `chapter_title` from yaml when no `#` header found.
- **LLM prompt** rewritten with strict JSON schema + 1-shot example. `_coerce_synopsis` joins list-typed outputs into a single string.
- **`BuildStats` dataclass** tracks token histogram + oversize count. Saved to `data/parsed/<book>/<chapter>_build_stats.json`. Notebook asserts `n_oversize == 0`.
- **`LIMIT_SECTIONS` knob** (`pipeline.run_chapter(limit_sections=N)`): preview ingest first N sections, manifest NOT written. CLI flag `--limit-sections`.
- `load_parents` / `save_parents` kept as no-op stubs in `build_documents.py` for backward compatibility.

## 2026-05-15 — Migrated Chroma → Qdrant (steps 20-31)

Reasons: built-in dashboard, native sparse vectors (drops BM25 pickle), multimodal-ready (named vectors), better metadata filtering, single binary.

- Image collection `stats_images` added per `ingestion/reference_image.md` schema. Vector = OpenAI embedding of `subsection + figure_caption`. CLIP visual embedding deferred.
- Sparse retrieval moved from `rank_bm25` pickle → Qdrant native sparse vector `bm25` via `fastembed` `Qdrant/bm25` model. RRF fusion server-side via `Prefetch` + `FusionQuery(Fusion.RRF)`.
- Manifest schema: `chroma_collection` → `qdrant_collection_text` + `qdrant_collection_images`.
- Tests `test_ingest.py` + `test_retrievers.py` deleted (stale). Need rewrite in future step.
- `data/chroma/` preserved on disk for rollback safety.

## 2026-05-15 — Ingestion v2 (steps 10-19)

Hybrid Claude + LLM extraction per `ingestion/reference.md` schema:

- Stages A (static) / B (regex) / C (LLM enrich) / D (parent+child docs at the time).
- ParentDocumentRetriever pattern: children 800c indexed, parents up to 25k chars returned. (Later dropped in step 35.)
- Embedding model upgraded `text-embedding-3-small` (1536d) → `text-embedding-3-large` (3072d).
- LLM provider: OpenAI nano V5 (`gpt-5.4-nano-2026-03-17`, 300k ctx) default; DeepSeek via OpenAI-compatible base_url.
- Manifest at `data/parsed/manifest.json` (versioned). Idempotency: `(book_slug, chapter_id) + chapter_hash`.
- ISLP bibliography unavailable (book has no back-matter References).

## 2026-05-15 — Initial pipeline (steps 1-9)

- Hybrid retrieval (dense + BM25) approved. Reason: textbook has technical terms benefiting from lexical match.
- OpenAI embeddings + Chroma server chosen over local HF/FAISS. Reason: quality, user preference.
- Markdown input only. User pre-cleans.
- BM25 persisted as pickle initially (no native sparse in Chroma). Reindex on doc add.
- Chroma host port changed 8000 → 8002 (8000 occupied).
- Ingest idempotency hardened: pre-filter via `store.get(ids=...)` before `add_documents`.
- Reviewer flag on Docker healthcheck path (`/api/v1` vs `/api/v2`) dismissed: v1 canonical for Chroma 0.5.x.

## Step table (audit trail)

| # | Step | Status |
|---|---|---|
| 1 | Scaffold | done |
| 2 | Docker Chroma | done |
| 3 | Config + ingest | done |
| 4 | Retrievers | done |
| 5 | Chain + CLI | done |
| 6 | Docs 3-level | done |
| 7 | Tests + eval | done |
| 8 | Review | done |
| 9 | Fix critical (ingest idempotency) | done |
| 10 | Ingestion v2 — schema + manifest + book yaml | done |
| 11 | Regex pass | done |
| 12 | LLM client factory | done |
| 13 | LLM enrich + cache | done |
| 14 | Parent-Doc build + retriever rewire + pipeline | done |
| 15 | Extract ISLP static metadata | done |
| 16 | Notebook 02 walkthrough | done |
| 17 | Notebook 03 retrieval tests | done |
| 18 | Notebook 04 provider parity | done |
| 19 | Run pipeline on ISLP ch02 | done (later re-run) |
| 20 | Qdrant docker | done |
| 21 | Config + requirements (Qdrant) | done |
| 22 | Qdrant store helper | done |
| 23 | Retrievers rewrite (Qdrant native RRF) | done |
| 24 | Schema + regex for images | done |
| 25-26 | Pipeline rewrite (Qdrant + images) | done |
| 27 | Notebook 05 Qdrant inspect | done |
| 28 | Notebook 03 migration | done |
| 29 | CLI --search-images, --book filter | done |
| 30 | Migration cleanup | done |
| 31 | Master notebook 00_run_all | done |
| 32 | H1 fallback from yaml | done |
| 33 | book_name in payload | done |
| 34 | Running page state + peek-back | done |
| 35 | Single-tier 8K token chunking | done |
| 36 | LLM prompt few-shot + coerce | done |
| 37 | BuildStats + monitoring | done |
| 38 | limit_sections preview mode | done |
| 39 | Docs restructure (system/) + skills | done |
| 40 | Per-field collections (`<field>_textbooks` + `<field>_images`); `field` key required in book yaml; ingestion auto-creates collection | done |
| 41 | regex_pass: numbered single-`#` headers (`# 1.1 Foo`) treated as sections (was eaten as H1) | done |
| 42 | pipeline guard: skip upsert on 0 chunks (was 400 from Qdrant) | done |
| 43 | Docs split: `docs/services/{ingestion,retrieval}.md`, `docs/guides/`, `docs/notes/`, `docs/state.md` autogen; CLAUDE.md trimmed to overview + service index | done |
| 44 | Code split: `src/retrieval/{retrievers,chain,cli}.py`; `src/eval/` placeholder; imports updated across notebooks + tests | done |
| 45 | Neal (Causal Inference) ingested as 3rd `introduction` book — 13 chapters, 90 chunks | done |
| 46 | Reorg: top-level `core/`, `ingestion/`, `services/<x>/`. Chinese-wall markers in `__init__.py`. Imports updated; docs/skills/notebooks/tests aligned. `library/_processed/` → `ingestion/processed/`. `docs/services/ingestion.md` → `docs/tasks/ingestion.md`. Commands: `python -m ingestion.pipeline …`, `python -m services.retrieval.cli …` | done |
| 47 | Top-level dim reduction 12→8 dirs. `library/` → `docs/library/`. `upgrades/` → `docs/upgrades/`. `references/` (empty) deleted. `scripts/`+`docker/` → `ops/{scripts,docker}/`. `image.png` → `docs/assets/`. Path refs updated in CLAUDE.md, skills, docs, README; render_state.py `parents[1]`→`parents[2]` | done |
| 48 | Top-level dim reduction 8→4 dirs: `src/` umbrella for `core,ingestion,services,tests`; `notebooks/` → `docs/notebooks/`. Imports: `from core.X` → `from src.core.X`, etc. Commands: `python -m src.ingestion.pipeline …`, `python -m src.services.retrieval.cli …`. `config.py ROOT`: `parent.parent` → `parent.parent.parent`. CLAUDE.md + skills + docs + notebooks aligned | done |
| 49 | Batch EPUB ingest (8 books, ~3.2k chunks): `stock_watson`+`murphy` (introduction), `pesaran`+`das`+`spark_ts` (econometrics), `goodfellow`+`prado`+`cerqueira` (ml_dp). 6 books dispatched via parallel sub-agents (~20 min wall vs ~2hr sequential). New preprocessor templates: HTML-span strip (S&W), TOC-link injection (Murphy/Goodfellow), italic-unwrap (Prado), markdown-link strip (Pesaran). Patterns documented in `src/ingestion/processed/*_preproc.py` | done |
| 50 | Deep tutor v2: `DeepTutorAnswer` 7-aspect schema (`tldr`/`definition`/`formal_statement`/`intuition`/`examples`/`trade_offs`/`further_reading`), parallel extract+RRF, density-select + scroll-expand, OpenAI structured streaming (real TTFB ~3-4s), critique loop off by default, reranker warm at import gated. 46s→17s p50. Docs at `docs/services/chat-features/36-deep-tutor.md` | done |
| 51 | Stale services cleanup: docker `statrag-chat`/`statrag-web` containers moved to `profiles: ["prod"]`; `./scripts/dev.sh` default port 8765→8766; vite proxy → :8766. Docs updated in `CLAUDE.md` and `docs/services/chat.md`. Dev (:8766/:5175) and prod (:8765/:5173) coexist | done |
| 52 | Conversation render fix: `api.py` persists structured `TutorAnswer` dict (not concatenated token stream) so reloaded convs render aspects; `App.tsx::handleSelectConv` revives legacy JSON-string content and assembles `text` from aspects | done |
| 53 | Deep-links: `http://localhost:5175/c/<id>` auto-loads conv via `pushState`+`popstate`; `#cite-<N>` opens Sources panel and scrolls to the citation card; sidebar `×` button + `DELETE /api/conversations/{id}` for removal | done |
| 54 | Right-rail transparency hydration: `LOAD_CONVERSATION` walks messages backward to populate `state.sources/figures/metadata` so ContextPanel works on reload | done |
| 55 | Image judge (two-tier): concept-density image retrieval + co-location boost, Tier-1 nano caption judge + Tier-2 vision (gpt-4o-mini) for borderline; `FigureRef` gains `aspect_hint`/`figure_role`/`judge_confidence`. Pipeline approves ≤3 figures, emits `figures_full` SSE event. `/api/figures` does path-remap for legacy ingest paths (`/Documents/Books/` → `/Documents/Converters/Books/`). Quality eval at `data/eval/image_label_set.csv` w/ auto-labeling oracle (`ops/scripts/auto_label_images.py`); first KPIs: precision 1.0, recall 0.864, F1 0.927, soft-placement 1.0 over 32 rows. Docs at `docs/services/chat-features/39-image-judge.md` and `docs/eval/image_label_instructions.md` | done |
| 56 | Tutor render: single-`*` italic fix in `web/src/components/views/TutorView.tsx` inline tokenizer (only `**bold**` handled; lone `*text*` leaked as literal). Added `<em class="tutor-view__em">` branch + plain-run break on `*`; CSS in `tutor.css`. First frontend test infra: `vitest` devDep + `npm test` + `TutorView.emphasis.test.tsx` (4 tests, renderToStaticMarkup) | done |
| 60 | Toolbar simplified: removed the **Model** picker and **CONFIG** (settings) buttons from the chat input bar (`InputBar.tsx` no longer renders `ModelPicker`/`SettingsPicker`; props dropped from `App.tsx`). Model selection now happens per-stage inside the About-Tutor modal diagram; `activeModel` state stays at its default and seeds the draft node. `ModelPicker.tsx`/`SettingsPicker.tsx` remain in the tree but unused. Settings (temperature/top_k/rerank) now always defer to backend defaults | done |
| 59 | About-model UI revision (feedback pass): `(i)` moved to the **Tutor card** in the Mode picker (`ModePicker.tsx`; removed from `ModelPicker.tsx`/toolbar — two prior placements were wrong). Diagram rebuilt earlier as SVG graph; node model pickers changed from native `<select>` to **custom dropdown** `NodeModelDropdown.tsx` (provider icons + grouped models, floating `position:fixed`, replicates chatbox picker). Modal capabilities now **bullet list + prose** (no card grid); modal sized **between side menus** (`fm__panel--about` 880px, `FocusModal` gains `panelClassName`); UI/UX type-scale pass on fonts. Tests updated in `PipelineDiagram.test.tsx` (custom dropdown, 11 FE tests pass). Iteration history documented in `docs/services/chat-features/41-about-model.md` | done |
| 58 | About-model feature: `(i)` on each model card opens a centered modal (`web/src/components/modals/AboutModelModal.tsx` via `FocusModal`) with description + capabilities (static `web/src/data/modelMeta.ts`) and an interactive tutor-pipeline diagram (`PipelineDiagram.tsx`, `data/tutorPipeline.ts`). Swappable LLM-text stages (expansion/draft/critique/image_judge) re-route to a picker chat model via `ChatRequest.stageModels`; locked stages (embedding/rerank/vision) shown but fixed. Backend: threaded a real `model` param through `extract_concepts`/`_stream_draft`/`critique`/`judge_image_candidates` (previously all hardwired to nano — the picker was cosmetic); draft now honors the picker model, OpenAI via native structured-stream + deepseek via best-effort `_stream_draft_via_router`. Tests: `test_stage_models.py` (reliability/integrity/relevance), `PipelineDiagram.test.tsx` (5). Docs: `docs/services/chat-features/41-about-model.md` | done |
| 57 | Tutor format pass (2026-05-20, 9 items). (#2) TL;DR heading → "Introduction" (internal key `tldr` kept; legacy convs still auto-expand). (#3) `<structure>` strengthened: no walls of text, framing sentence + lists for dense aspects. (#4) Introduction = direct answer + one-sentence roadmap (schema `tldr` desc updated). (#5) `further_reading` adds 2-3 open/related research questions. (#6) `synthesis_rules` now per-claim attribution — no pooling 2 sources behind one `[N]`; definition prefers one bullet/source. (#7) `formal_statement` reproduces book theorem **verbatim** as `>` blockquote + `[N]` (overrides 15-word limit), else indirect cite; added blockquote support to `TutorView` parser + `.tutor-view__quote` CSS. (#8) example relevance audit: prompt self-note "**Why this example fits:**" + deterministic `_score_example_relevance` → `TutorAnswer.quality["example_relevance"]`. (#9) vision-explain: `build_vision_explanations` + `_explain_figure_vision` read each placed figure (gpt-4o-mini) and explain it vs the concept; gated by `TUTOR_DEEP_VISION_EXPLAIN=1` (default off); `<figures>` prompt now requires conceptual link to definition/statement. Tests: `test_tutor_prompt_contract.py` (prompt contracts + scorers), `TutorView.emphasis/blocks.test.tsx`. Full suites green | done |
