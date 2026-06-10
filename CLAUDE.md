# RAG — Statistical Textbooks

Local-first Retrieval-Augmented Generation over OCR-processed textbooks. Hybrid retrieval (dense + sparse) over per-field Qdrant collections, plus separate image collections for figures.

## Stack

- **Vector DB**: Qdrant 1.12.4 in Docker, dashboard at `http://localhost:6333/dashboard`
- **Embeddings**: `text-embedding-3-large` (OpenAI, 3072d)
- **LLM (chat)**: `gpt-5.4-nano-2026-03-17` (default), `deepseek-v4-pro`, or Groq (`meta-llama/llama-4-scout-17b-16e-instruct`, `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`). Groq is chat-only. **Ingestion enrichment** defaults to DeepSeek `deepseek-v4-flash` (non-thinking, cheap) via `--provider`; embeddings + image captioning stay OpenAI. See [`docs/tasks/ingestion.md`](docs/tasks/ingestion.md#llm-provider-for-enrichment).
- **Sparse**: Qdrant native `bm25` via `fastembed`
- **Chunking**: 1 section = 1 chunk, split at 8000 tokens (tiktoken `cl100k_base`)
- **Language**: Python 3.12 in `.venv`

## Quick start

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
.venv/bin/python -m pip install -r requirements.txt          # one-time
ln -sf /home/iohan/Documents/toolbox/tools/AI_brain/Tools/Book_analyzer/.env .env
docker compose -f ops/docker/docker-compose.yml up -d        # Qdrant only (dev)
./scripts/dev.sh                                             # default app entry — Vite :5175 + backend :8766
```

**Dev vs prod ports:**
- **Default workflow: `./scripts/dev.sh`** → frontend on **:5175** (use this URL). Runs backend natively on **:8766** and Vite on **:5175** (proxied).
- `docker compose up -d` brings up **Qdrant only**.
- Prod containers (`statrag-chat` :8765, `statrag-web` :5173) live under the `prod` profile: `docker compose --profile prod up -d`.
- Dev and prod ports are intentionally different so the two can coexist without conflicts.

## Top-level layout (4 dirs)

```
src/                        ALL code (one umbrella)
  core/                     shared infra (config, qdrant_store) — imports nothing in repo
  ingestion/                task — code + books/ + processed/
    books/                  per-book yaml configs
    processed/              preprocessor scripts + fixed sources
  services/                 user-facing features
    retrieval/              hybrid query + chain + CLI
    chat/                   SSE chat backend (FastAPI) — Part 2
    eval/                   placeholder

web/                        React + Vite + TS SPA — Part 2 frontend
  tests/                    pytest

data/                       DB-derived artifacts (sections, images, manifest)

docs/                       ALL documentation + notebooks
  tasks/ingestion.md        operational doc per task
  services/retrieval.md     operational doc per service
  system/                   architecture, invariants, changelog
  library/                  per-collection registry markdown
  upgrades/                 future-services roadmap (abstract.md)
  guides/                   easy/medium/specialist
  notes/                    historical reviews
  assets/                   images
  notebooks/                jupyter notebooks (entry point + experiments)
  state.md                  auto-generated registry

ops/                        operational tooling
  scripts/                  utilities (render_state.py)
  docker/                   container configs (Qdrant)
```

## Architecture — Chinese wall

| Layer | Folder | Rule |
|---|---|---|
| **Core** (system) | `src/core/` | Shared infra. Imports nothing in repo. |
| **Tasks** (external-input → DB) | `src/ingestion/` | One-off processes. Read external sources, write to DB. Imports only `src.core`. |
| **Services** (DB → user features) | `src/services/<name>/` | Each service is a subpackage. Imports only `src.core`. Services never import from each other or from tasks. |

Wall is encoded in each `__init__.py`. Add new services as `src/services/<name>/`; add new tasks as siblings of `src/ingestion/`.

## Where to look

| What | Path |
|---|---|
| **Ingestion ops** | [`docs/tasks/ingestion.md`](docs/tasks/ingestion.md) |
| **Retrieval ops** | [`docs/services/retrieval.md`](docs/services/retrieval.md) |
| **Chat service ops** | [`docs/services/chat.md`](docs/services/chat.md) |
| **Chat feature deep-dive** | [`docs/services/chat-features/`](docs/services/chat-features/README.md) — 39+ per-feature docs w/ graphs; recent: 36 deep-tutor, 39 image-judge, 42 author-diversity, 43 synthesis-plan, 44 orchestrator-workers, 45 query-planner-coverage, 46 adjacency-recall, 47 answer-coherence, 48 long-context-organizer, 49 subsections-and-citation-links, 50 groq-provider-and-prompt-schema, 51 qa-mode, 52 book-scope-resolve, 53 facilitate-concept-map, 54 extension-mode |
| **Image eval** | [`docs/eval/image_label_instructions.md`](docs/eval/image_label_instructions.md) — labeling guide + KPIs; live runner via `pytest -m quality_images` |
| **Chat next step** | **Resume mode** — (1) remake the resume digest layout (frontend rendering), (2) certify its structured-output JSON structure is implemented (resume runs via `chapter.py`, already routed through `apply_structured_output` — confirm the scaffolded prompts + per-call schemas hold end-to-end). See [`docs/services/chat-features/53-facilitate-concept-map.md`](docs/services/chat-features/) + chapter prompts in `src/services/chat/prompts/chapter.py`. |
| **Architecture** | [`docs/system/architecture.md`](docs/system/architecture.md) |
| **Invariants** | [`docs/system/invariants.md`](docs/system/invariants.md) |
| **Changelog** | [`docs/system/changelog.md`](docs/system/changelog.md) |
| **Live state** | [`docs/state.md`](docs/state.md) (regen via `ops/scripts/render_state.py`) |
| **Collection registries** | [`docs/library/<collection>.md`](docs/library/) |
| **Future services** | [`docs/upgrades/abstract.md`](docs/upgrades/abstract.md) |
| **Per-book config** | `src/ingestion/books/<slug>.yaml` |
| **Preprocessors** | `src/ingestion/processed/` |

## Collections (live)

Per-field naming: `<field>_textbooks` + `<field>_images`. `field` comes from book yaml; collection auto-created on first ingest. See [`docs/state.md`](docs/state.md) + [`docs/library/`](docs/library/).

## For Claude sessions

A fresh Claude session must:

1. Read `docs/system/architecture.md` before touching ingestion code.
2. Read `docs/system/invariants.md` before changing prompts or chunking.
3. **Respect the Chinese wall**: `src/core/` imports nothing in repo; services never import from each other or from `src/ingestion/`.
4. To ingest a book → invoke `rag-add-book` skill. Three user gates apply (yaml, preview, full). Never auto-proceed.
5. **After a successful full ingest**: append a row to `docs/library/<collection>.md` (create if new collection). Row fields: slug, name, authors, year, edition, theme, chapters, chunks, images. Pull from `src/ingestion/books/<slug>.yaml` + `data/parsed/manifest.json`.
6. To verify state → invoke `rag-verify` skill.
7. To understand prior decisions → read `docs/system/changelog.md`.

### ⏳ Pending tasks (pick up next session)

When the user says **"pending tasks"**, **"what's next"**, **"resume formula recovery"**, or
starts a fresh session asking what to do, read this list and the linked spec/plan:

| Pending | Status | Spec / plan |
|---|---|---|
| **Formula recovery + global cache** — gap-triggered second-RAG: when a concept's defining equation was OCR-dropped to an image, gpt-4o **vision reads the equation off the figure** (`search_figures`+`inspect_figure` w/ transcription instruction), text re-query fallback, fed into the synth as `<recovered_equations>` (used verbatim); recovered equations cached globally in a `formula_cache` Qdrant collection for consistency/cost. Lightweight `asyncio.gather` (no deepagents). | ✅ **shipped** (branch `feat/ow-harness-pland`) — modules `formula_gaps.py`/`formula_cache.py`/`formula_recovery.py`; wired into `run_orchestrator_workers`; modal + 36 mermaid + invariant 37 + doc 56 lockstep done. Pending: live manual verify on :5175 (real gpt-4o $). | [spec](docs/superpowers/specs/2026-06-04-formula-recovery-and-cache-design.md) · [plan](docs/superpowers/plans/2026-06-04-formula-recovery-and-cache.md) |
| **Deep-synth formulas wrong + Bias/Variance missing formulas** — the orchestrator-deep answer renders incorrect formulas and the `### Bias`/`### Variance` subsections lack their defining equations. **Inspect first:** conv `http://localhost:5175/c/9e0a393d5bd047dd8c8129d9704c172c`. Needs a **full-workflow** fix (workers preserve equations → formula recovery actually lands `<recovered_equations>` verbatim in the Bias/Variance subsections → synth prompt/structure → schema), per invariants 23 + 37. Diagnose with an OpenAI model (nano) so Groq JSON flakiness doesn't mask it; note `data/cost_log.jsonl` is NOT written by the tutor path. | ⏳ **NEXT — flagged 2026-06-04, not started.** | (none yet — start with the conv above) |
| **Plan D — productionize L3b** (deepagents) + lean-structured follow-on | ✅ shipped — live deep path routes to fast L0 structured synth (no `_schema_fill`); deepagents agents (levels 6/7) eval-only; component-equation verbatim/reconstruct + worker preserve-equations. | [doc 56](docs/services/chat-features/56-deep-synthesis-l3b.md) |
| **Q&A deepagent rebuild (roster + thesis/body/conclusion + checker loop)** — replace the flat 4-node Q&A with a scoped agentic-retrieval **deepagent**: `scope → gate(simple‖compound) → orchestrator(search loop ‖ analyst subagents) → organize(merge/drop repeats) → checker(env-capped re-call loop)`. Output = fixed **thesis → body → conclusion** progression. 4-agent roster (scope/orchestrator/analyst/checker), each with `AGENTS.md` + tools + skills + `<task>`-scaffolded prompt; 3 Open-Agent `SKILL.md` (grounded-qa, synthesize-progression, critique-coverage). Incorporates k-dense-ai/scientific-agent-skills + skillsllm deep-research patterns. **Hard tutor-isolation** (own `qa_skills/`+`qa_agents/`, zero tutor imports). Spec + plan written, **not started** — 10 TDD tasks, run via subagent-driven-development w/ sonnet. | ⏳ **NEXT IMPLEMENTATION — flagged 2026-06-08, not started.** | [spec](docs/superpowers/specs/2026-06-05-qa-deepagent-design.md) (rev 2026-06-08) · [plan](docs/superpowers/plans/2026-06-08-qa-deepagent-roster.md) |
| **Extension mode** — `extension` chat mode (deepagents topology C; corpus+Wikipedia footnote augmentation; styled-HTML ZIP export). **✅ MERGED into `feat/component-equation-enforcement` 2026-06-10** (was branch `worktree-feat+extension-mode`; 875 backend / 238 frontend tests green, tsc clean). 2026-06-10 polish batch (changelog top entry): QA black-screen guard ported + single `StructuredErrorBoundary` in MessageThread; digest markdown rendering (bold/italic, `[^n]` strip, marker dedupe) + legacy math-delimiter normalization on render; runner stamps authoritative `digest.book`/`digest.chapter` (honest narrowed label, e.g. `ch07 · 7.4–7.5`) + section-number word-boundary subtopic matching; lost answer for conv `9d9985d3…` RECOVERED into that worktree's `data/chat.db` via `ops/scripts/backfill_extension_conv.py` (20 points/20 footnotes, live-verified); orchestrator now directs parallel analyst task fan-out. **NOTE: extension conversations still live ONLY in the worktree's own `data/chat.db`** — run `./scripts/dev.sh` FROM `.claude/worktrees/feat+extension-mode` to see them (each checkout has its own chat.db). **Remaining follow-ups:** (a) live timing run to confirm parallel-analyst speedup (~17min baseline); (b) language drift (Polish) in long runs — prompt-level, unresolved; (c) ZIP filename embeds `·`/`–` from chapter label (cosmetic); (d) optional: migrate worktree chat.db convs into main checkout db. | ✅ **merged 2026-06-10; superseded by Extension v2 below** | [spec](docs/superpowers/specs/2026-06-09-extension-mode-design.md) · [plan](docs/superpowers/plans/2026-06-09-extension-mode.md) · [doc 54](docs/services/chat-features/54-extension-mode.md) |
| **Extension v2 — story timeline + curiosity boxes (REBUILD)** — deterministic async pipeline replacing deepagents core: `scope → fetch → storyteller×N → story_editor → subject_miner×take → researcher×subject (PURE CODE) → curiosity_writer×take → citation_binder (PURE CODE, verbatim payload citations) → judge (one retry) → StoryDigest`. `StoryDigestCard` (timeline rail, curiosity toggle, corpus/wiki chips). Legacy `ExtensionDigest` convs keep old card. 874 backend / 250 frontend tests green. **BUILT on branch `feat/extension-v2-story-curiosity` — live verify pending.** | ⏳ **live verify pending (Task 15)** | [spec](docs/superpowers/specs/2026-06-10-extension-v2-story-curiosity-design.md) · [plan](docs/superpowers/plans/2026-06-10-extension-v2-story-curiosity.md) · [doc 54](docs/services/chat-features/54-extension-mode.md) |



### Shortcut: `feature_Agent`

When the user asks for a **`feature_Agent`** (or "be the feature agent" / "feature agent mode"), immediately **read `docs/common ground/Agents/feature_Agent.md` and transform yourself into it** — adopt its workflow, skills, and definition of "done". Use it for any feature that touches the deep-tutor pipeline (new/changed stage, knob, retrieval/diversity/coverage/draft behaviour). It enforces the interconnected-artifact rule below and the preview → execute → test → update-docs chain.

### Shortcut: `system_Agent`

When the user asks for a **`system_Agent`** (or "be the system agent" / "system agent mode"), immediately **read `docs/common ground/Agents/system_Agent.md` and transform yourself into it**. Use it for full-stack **system** features — anything that is NOT a deep-tutor pipeline stage: FastAPI routes / SSE contract, request/response schemas, core infra (`src/core/`), the React/Vite/TS frontend (components, views, state, modal, math render), build config, and the Docker/ops layer. It loads the full toolchain (Python 3.12 + FastAPI/uvicorn/pydantic/openai/qdrant/sentence-transformers/…, TypeScript + React/Vite/vitest/katex, Docker/compose) and enforces the same preview → execute → test → browser-verify (:5175) → update-docs chain, keeping backend↔schema↔SSE↔frontend in lockstep. When a change spans both, do the pipeline part as `feature_Agent` and the rest as `system_Agent`.

### Every pipeline stage spans synced artifacts — change them in lockstep

Each tutor pipeline stage / agent (concept→query planner, retrieval, density+rerank, author-diversity, coverage check, figure-judge, planner, drafting workflow + orchestrator-workers, vision-explain, …) is **not one file**. Its behaviour, its prompt, its request knobs, its diagram node, and its docs are separate artifacts that MUST stay consistent. When you modify a stage's logic, look up and update ALL of these:

| Aspect | Where |
|---|---|
| **Backend logic** | `src/services/chat/agents/deep_tutor.py` (+ `orchestrator_workers.py`, `coverage.py`) |
| **Prompts** | `src/services/chat/prompts/deep_tutor.py` |
| **Request knobs / response schema** | `src/services/chat/schemas/_core.py` (request), `schemas/output.py` (models) |
| **Env flags** | the stage's `TUTOR_*` var + env table in `docs/services/chat-features/36-deep-tutor.md` |
| **Modal card (the graph users see)** | `web/src/data/tutorPipeline.ts` (nodes/edges/labels) + `web/src/components/PipelineDiagram.tsx` (layout/render) |
| **Backend mermaid graph** | `docs/services/chat-features/36-deep-tutor.md` |
| **Per-feature doc** | `docs/services/chat-features/<NN>-<feature>.md` |
| **Reference design graph** | `docs/common ground/Elements/home.html` (entry) — multi-page current-state doc set. Nav: **Overview** (`index.html`), **Verification** (`report.html`), and toggle groups **Ingestion** (`ingestion/{index,pipeline,chunking,preprocessors}.html`), **Features** (`features/index.html` + `modes/{tutor,qa,facilitate,resume}.html` — 2 diagrams per mode), **Services** (`services/{index,core,ingestion,retrieval,chat,eval}.html`), **Models** (`models/index.html` + per-model). This is the **single source of HTML documentation** — old top-level `Elements/{chat,ingestion,retrieval}.html` and the legacy `Demo/ChatSystem/statrag.html` stubs were removed (merge of `docs/statrag-html-docs`, 2026-06-09). |
| **Invariants + changelog** | `docs/system/invariants.md`, `docs/system/changelog.md` |
| **Tests** | `src/services/chat/tests/test_*.py` + `web/src/components/PipelineDiagram.test.tsx` |

Rule: a logic change is **incomplete** until the **modal card** (`tutorPipeline.ts`/`PipelineDiagram.tsx`), the **docs/graphs**, and the **tests** all reflect it. After a diagram/stage change, **open the tutor (i) modal in the browser on :5175 and confirm it visually matches** `docs/common ground/Elements/modes/tutor.html` (the tutor mode page now holds the deep-tutor pipeline diagram) — the modal is the source of truth users see, and it has drifted before.

Commands:
- Ingest: `python -m src.ingestion.pipeline --book <slug> --chapter chNN --force`
- Status: `python -m src.ingestion.pipeline --status`
- Retrieval CLI: `python -m src.services.retrieval.cli "<question>" --book <slug>`
- Chat dev (backend + frontend, **default — use :5175**): `./scripts/dev.sh` (FastAPI :8766 + Vite :5175, vite proxy /api -> :8766)
- Chat backend alone: `.venv/bin/python -m uvicorn src.services.chat.api:app --reload`
- Frontend deps (one-time): `cd web && npm install`
- Regen state: `python ops/scripts/render_state.py`
- Qdrant up: `docker compose -f ops/docker/docker-compose.yml up -d`

Skills enforce invariants + cost-controlled preview-then-confirm. Do not bypass.
