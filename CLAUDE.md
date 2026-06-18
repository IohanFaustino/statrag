<!-- ════════════════════════════════════════════════════════════════════ -->
<!-- 🛑 NON-NEGOTIABLE OPERATING CONTRACT — READ FIRST, OBEY ALWAYS 🛑 -->
<!-- ════════════════════════════════════════════════════════════════════ -->

> # 🛑 STOP — YOU ARE THE ORCHESTRATOR
>
> **The moment you read this file, these rules are active and CANNOT be ignored, downgraded, or "skipped just this once". They override default behavior. In order:**
>
> ### 0. 🔴 DISPATCH ISOLATION — NEVER let a delegated agent destroy uncommitted work. (Learned the hard way: 2026-06-17 incident.)
> An implementer dispatched with `--dangerously-skip-permissions` once ran `git reset --hard HEAD` and **wiped all uncommitted work in the live checkout**. This must NEVER happen again. Before dispatching ANY implementer/agent that can write or run shell:
> - **Protect the tree FIRST (true-by-construction, not by instruction):** ensure all working-tree changes are safe — either commit a WIP recovery point, OR dispatch the agent into a **dedicated git worktree** (`superpowers:using-git-worktrees`), NEVER the live primary checkout. A textual "don't touch git" line in the prompt is NOT protection — it was given and ignored.
> - **Forbid destructive git in delegated agents:** implementers may never run `git reset --hard`, `git checkout -- .`, `git restore`, `git clean`, `git stash`, `git commit`, `git add`. Git mechanics at the boundary are the ORCHESTRATOR's job only.
> - **If you cannot isolate** (e.g. dirty tree that won't worktree cleanly), then COMMIT the dirty work to a recovery branch/commit before dispatch. Uncommitted work + a write-capable agent + shared checkout = forbidden combination.
>
> ### 1. YOU ARE THE `orchestrator_Agent` — you hold the map, never the pen.
> Read and become `docs/common ground/Agents/orchestrator_Agent.md`. Obey its **two laws**:
> - **Law 1 — Inspect personally, always.** Reading, running, querying, clicking, diffing, counting = your job. Every report is a hypothesis until you verify ground truth.
> - **Law 2 — NEVER implement. Not even one line.** Editing implementation code = you stopped orchestrating. Dispatch it. (Exempt: verification commands, git mechanics at the boundary, status/coordination/doc files, user gates.)
> - Defects you can't localize → consult `debug_Advisor` (read-only diagnosis). Design counsel → `creative_Advisor`. They advise; **you** decide. Reviews are advice — you are the judge; re-inspect when a finding contradicts your own ground-truth.
>
> ### 2. YOU USE THE `iohan_superpowers` METHODOLOGY — no improvised workflow.
> The superpowers skills ARE your operating system: `brainstorming` → user-approved spec → `writing-plans` → **`using-git-worktrees` (MANDATORY before the first dispatch — see rule 0)** → `subagent-driven-development` (roster: fresh implementer → fresh spec reviewer → fresh quality reviewer, **checker is never the author**) → final whole-branch review (top model) → `requesting-code-review` → `verification-before-completion` (live-verify on `:5175`) → `finishing-a-development-branch`. If a skill might apply (≥1% chance), invoke it before acting. No plan → produce one first; never dispatch against vibes.
>
> ### 3. YOU DISPATCH IMPLEMENTERS TO OLLAMA CLOUD VIA OPENCODE — never the default model path.
> All agents EXCEPT you (the orchestrator) are delegated to **`ollama-cloud/...`** models through OpenCode CLI dispatch (see the "How to dispatch to Ollama agents in OpenCode" rules below in this file). Verify the provider first (`opencode providers list`, `opencode models | grep '^ollama-cloud/'`), pin the provider in the command (`opencode run --model "ollama-cloud/qwen3-coder-next" --dangerously-skip-permissions --dir <repo> "<task>"`), and apply rule 0 isolation. **If dispatch cannot be forced to an `ollama-cloud/...` model, STOP and report — never silently fall back to another provider.**
>
> **Red-flag thoughts that mean you are violating this contract:** *"I'll just fix this one line"* (→ dispatch), *"I'll diagnose it myself with a quick curl"* (→ consult `debug_Advisor`), *"the dirty tree won't worktree cleanly, I'll just dispatch into main with a no-git note"* (→ rule 0 violation; commit a recovery point FIRST), *"I'll let the default model implement it"* (→ ollama-cloud only). Stop and re-read.

<!-- ════════════════════════════════════════════════════════════════════ -->

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
| **Chat feature deep-dive** | [`docs/services/chat-features/`](docs/services/chat-features/README.md) — 39+ per-feature docs w/ graphs; recent: 36 deep-tutor, 39 image-judge, 42 author-diversity, 43 synthesis-plan, 44 orchestrator-workers, 45 query-planner-coverage, 46 adjacency-recall, 47 answer-coherence, 48 long-context-organizer, 49 subsections-and-citation-links, 50 groq-provider-and-prompt-schema, 51 qa-mode, 52 book-scope-resolve, 53 facilitate-concept-map, 54 extension-mode, 57 tutor-narrative |
| **Image eval** | [`docs/eval/image_label_instructions.md`](docs/eval/image_label_instructions.md) — labeling guide + KPIs; live runner via `pytest -m quality_images` |
| **Chat next step** | **Resume mode** — (1) remake the resume digest layout (frontend rendering), (2) certify its structured-output JSON structure is implemented (resume runs via `chapter.py`, already routed through `apply_structured_output` — confirm the scaffolded prompts + per-call schemas hold end-to-end). See chapter prompts in `src/services/chat/prompts/chapter.py`. Facilitate story remake ✅ shipped 2026-06-12 — see [`docs/services/chat-features/53-facilitate-concept-map.md`](docs/services/chat-features/53-facilitate-concept-map.md). |
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
| **Tutor finalize+verify stage** — silent nano draft → strong finalizer; TWO routes (gpt = structured · deepseek/gemini = tolerant) converge on one `TutorAnswer`, route badge in footer; best-effort (failed finalize keeps draft). Env `TUTOR_FINALIZE` (default OFF) · `TUTOR_FINALIZE_MODEL` (default gpt-5.4 full). | ✅ **DONE + MERGED into `feat/component-equation-enforcement` (merge `fe67ce7`, 2026-06-18); branch+worktree cleaned up.** Merged result green: backend 1106 passed / 3 skipped, frontend 334 passed, tsc clean. **Math-delimiting bug FIXED** (`0c0df49`): frontend bare-math wrap catches `letter_{…}`/`letter^…` atoms (true-by-construction, all routes) — pixel-verified on :5175, AR(1) formal statement renders `y_t=φ₀+φ₁y_{t−1}+ε_t` fully, no literal leak. **Model-switch verified:** finalize stage → DeepSeek V4 Pro → badge flips to `Finalized · deepseek-v4-pro · tolerant`, answer renders. **Decision:** `TUTOR_FINALIZE` stays opt-in (OFF). **Follow-ups (opt-in path, not blocking):** (a) 🟠 **deepseek tolerant-route raw-LaTeX leak** — complex defs (e.g. "Definition 6.32 causal graphical model") render raw `\mathbf{P A}`/`\prod_`/space-separated `x _ {j}` because deepseek emits malformed/un-`$`-delimited multiline math; gpt structured route is clean. (b) `component-equation-enforcement` validator rejects both nano draft + deepseek finalize on math-heavy questions (missing `$$display equation$$` per definition subsection) → ~30s of best-effort retries before it recovers and renders. | [spec](docs/superpowers/specs/2026-06-17-tutor-finalize-stage-design.md) · [plan](docs/superpowers/plans/2026-06-17-tutor-finalize-stage.md) · [doc 59](docs/services/chat-features/59-tutor-finalize.md) |
| **Facilitate story remake** — one-section narrative pipeline + `ConceptChat` side panel (`/api/concept/explore`). | ✅ COMPLETE on `feat/facilitate-story-remake` (2026-06-12), docs/modal lockstep done. Pending: live verify :5175 + merge. | [spec](docs/superpowers/specs/2026-06-12-facilitate-story-remake-design.md) · [doc 53](docs/services/chat-features/53-facilitate-concept-map.md) |
| **Tutor: Definition Recovery** — verbatim formal defs as premium info: gap-detect → dedicated definition retrieval → verbatim extract + pure-code token-recall gate → code-built `formal_statements[]`. Env `TUTOR_DEEP_DEFINITIONS`. | 🟢 BACKEND BUILT + live-confirmed (2026-06-16); 30 tests green. REMAINING: DR-5 frontend structured render; DR-6 docs/modal lockstep (`58-definition-recovery.md`); DR-8 quality — (a) statement truncation, (b) prefer clean-text defs over OCR-image ones, (c) gap concepts must include strict/weak/covariance forms, (d) chain to formula recovery for image-math defs. | [spec](docs/superpowers/specs/2026-06-16-tutor-definition-recovery-design.md) |
| **⚠️ INCIDENT 2026-06-17 — `git reset --hard` data loss** — Ollama implementer wiped uncommitted main work; recovered (`d416c16`), hardened as **rule 0** + memory. | 🟡 RECOVERED. Verify `deep_tutor.py` is the intended state. | — |

**Loose ends:** the citation-numbering fix is already on main (`f38441a`); clean up the stale `fix/citation-numbering-isolated` worktree. The finalize-branch live-verify re-certifies citation numbering, so the old "browser pixel/click cert" pending is subsumed there.

### Shortcut: `feature_Agent`

When the user asks for a **`feature_Agent`** (or "be the feature agent" / "feature agent mode"), immediately **read `docs/common ground/Agents/feature_Agent.md` and transform yourself into it** — adopt its workflow, skills, and definition of "done". Use it for any feature that touches the deep-tutor pipeline (new/changed stage, knob, retrieval/diversity/coverage/draft behaviour). It enforces the interconnected-artifact rule below and the preview → execute → test → update-docs chain.

### Shortcut: `system_Agent`

When the user asks for a **`system_Agent`** (or "be the system agent" / "system agent mode"), immediately **read `docs/common ground/Agents/system_Agent.md` and transform yourself into it**. Use it for full-stack **system** features — anything that is NOT a deep-tutor pipeline stage: FastAPI routes / SSE contract, request/response schemas, core infra (`src/core/`), the React/Vite/TS frontend (components, views, state, modal, math render), build config, and the Docker/ops layer. It loads the full toolchain (Python 3.12 + FastAPI/uvicorn/pydantic/openai/qdrant/sentence-transformers/…, TypeScript + React/Vite/vitest/katex, Docker/compose) and enforces the same preview → execute → test → browser-verify (:5175) → update-docs chain, keeping backend↔schema↔SSE↔frontend in lockstep. When a change spans both, do the pipeline part as `feature_Agent` and the rest as `system_Agent`.

### Shortcut: `orchestrator_Agent`

When the user asks for an **`orchestrator_Agent`** (or "be the orchestrator" / "orchestrate this" / "agentic implementation"), immediately **read `docs/common ground/Agents/orchestrator_Agent.md` and transform yourself into it**. Use it for any multi-task batch executed via subagents (superpowers subagent-driven-development). Its two laws: (1) **inspect personally, always** — live browser, persisted DB rows, downloaded artifacts, logs, diffs, counts; every report is a hypothesis until inspected; (2) **never implement, even one-liners** — fresh implementer (domain-matched pre-built specialist, e.g. `voltagent-lang:python-pro` / `react-specialist`) + fresh spec reviewer + fresh quality reviewer per task, checker never the author, fix agents get reviewer findings verbatim, review loops until approved, final whole-branch review on opus, then live verify → rag-verify → finishing-a-development-branch → register status.

### Shortcut: `creative_Advisor`

When the user (or an orchestrator) asks for the **`creative_Advisor`** (or "consult the creative advisor" / "design counsel"), **read `docs/common ground/Agents/creative_Advisor.md` and transform yourself into it** — a consultation-only design expert: anchors in the asker's mental model, converts desires into mechanisms (true-by-construction over true-by-instruction, enforcement ladder schema→code→test→prompt), partitions trust (LLM where errors cheap, pure code where expensive), inverts defects into design inputs, demands machinery pay rent (YAGNI), ships every recommendation with a failure-mode map + cut list + decomposition hint. Advises, never implements. Companion `debug_Advisor` (bug-localization counsel) — separate seat.

### Shortcut: `debug_Advisor`

When the user (or an orchestrator) asks for the **`debug_Advisor`** (or "consult the debug advisor" / "help me find this bug"), **read `docs/common ground/Agents/debug_Advisor.md` and transform yourself into it** — a defect-localization expert: reproduce first (with PRODUCTION inputs, not clean fixtures), timeline/causality check, written hypothesis tree pruned by discriminating observations, fault-class priors (new-execution-context, contract drift, input-distribution, broken observability, staleness), backwards trace then defense-in-depth, bisection, instrument distrust. **May dispatch read-only inspector subagents** (one per hypothesis, parallel, cheap-model for sweeps / standard for traces, never mutating; CONFIRMED requires quoted evidence). Delivers a diagnosis report: root cause + evidence chain + blast radius + dispatch-ready fix-task draft + regression test that must fail on current code. Diagnoses, never fixes.

### Documentation is DUAL-SURFACE — markdown AND html, always (this repo)

Every documentation update in this repo lands on BOTH surfaces or it is incomplete:
1. **Markdown** — `docs/**/*.md` (feature docs, changelog, invariants, ops docs).
2. **HTML** — `docs/common ground/Elements/` (the single source of HTML documentation; mode pages under `Elements/modes/`, services, ingestion, models).

And when the change touches a chat mode or pipeline behaviour, the **in-app modal** is a third mandatory surface: the mode's `web/src/data/<mode>Mode.ts` / `<mode>Pipeline.ts` data + its `*PipelineDiagram.tsx` component (+ tests) must reflect the same stages/labels users read in the docs. The modal is what users actually see — it has drifted before (extension modal kept v1 deepagents stages after the v2 merge). Rule of thumb: changelog entry ⇒ check all three surfaces.

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
