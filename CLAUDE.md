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
| **Facilitate story remake** — single-section narrative pipeline replacing the chapter-loop design: `parse → fetch ONE section (closest-match+confirm) → map (concept anchors) → write story (hook/movements/takeaway, verbatim formal statements unpacked) → bind (PURE CODE, provenance+citations verbatim) → verify (PURE CODE, statement fidelity token-recall)`. `FacilitateStoryCard` + `ConceptChat` side panel (`POST /api/concept/explore`, stateless). `FacilitateDigest` kept for legacy stored convs. 9 tasks via subagent-driven-development + creative-advisor. All 9 tasks complete + docs lockstep done (T9). **Gates: 300 frontend tests green, tsc clean.** Pending: live verify on :5175 + rag-verify + merge. | ✅ **COMPLETE on branch `feat/facilitate-story-remake` (2026-06-12); docs/modal lockstep done (T9). Live verify + merge pending.** | [spec](docs/superpowers/specs/2026-06-12-facilitate-story-remake-design.md) · [plan](docs/superpowers/plans/2026-06-12-facilitate-story-remake.md) · [doc 53](docs/services/chat-features/53-facilitate-concept-map.md) |
| **Tutor: Definition Recovery (verbatim formal defs as PREMIUM info)** — ACTIVE design (2026-06-16). Root-cause of the missing formal defs: (1) the formal definition (e.g. Hansen strict/weak stationarity) is never RETRIEVED to top-k by the general query, and (2) the draft paraphrases it. Fix mirrors the live `formula_recovery` trio: new `definition_gaps.py`/`definition_recovery.py`/`definition_cache.py` — gap-detect → DEDICATED definition-shaped retrieval per concept (surfaces Hansen) → LLM-extract verbatim span + PURE-CODE token-recall fidelity gate → Qdrant `definition_cache` → **CODE builds `formal_statements[]` (true-by-construction; draft weaves prose, can't paraphrase)** → override `answer.formal_statements`. Env `TUTOR_DEEP_DEFINITIONS`. Reuses TutorFormalDef schema (`29dc332`) + render (`507e3b3`). To be implemented via the Ollama agent layer (`tools/ollama_agents/`). Live gate: stationarity → verbatim strict+weak shown. | 🟢 **BACKEND BUILT + CORE VERIFIED (2026-06-16).** Phases DR-1..4 all via Ollama agents (`e840555`→`8b28d05`) + import fix (`28dfb51`); 30 DR unit tests + full chat suite green. **DIRECT CORPUS VERIFY:** `recover_definitions(["strict stationarity","weak stationarity"])` returns 2 VERBATIM defs from `das ch09 §9.2.1.1` ("A time series process y_t is strictly stationary or strongly stationary if the joint probability distribution…depends only on the lag length…" + "…weakly stationary or covariance stationary if its first- and second-order moments are unaffected by a change in time origin") — premium info the general retrieval never surfaced. Bug found+fixed: `apply_structured_output` import was from `llm.router` not `llm.structured` (mocked tests had patched past it → silent 0 recovered); regression test added. **REMAINING:** DR-5 frontend structured `formal_statements[]` render (markdown path already surfaces them); DR-6 docs/modal lockstep + new doc 58; DR-5 frontend structured render; DR-6 docs/modal lockstep + doc 58. **DR-7 END-TO-END LIVE CONFIRMED on :5175 (2026-06-16):** the stationarity query now renders a **"Formal statement" section** (ABSENT before) — "Definition 15. The stochastic process … is said to be str… [11]" — code-built from recovery, cited at rank [11], 0 console errors. Architecture PROVEN. **Two refinements (DR-8):** (a) the recovered statement is TRUNCATED ("…str") — extract/render cut mid-word; (b) source SELECTION picked pesaran "Definition 15" whose math is OCR image-placeholders (`![image](…gif)`) over the CLEAN text def in `das ch09 §9.2.1.1` that the direct test recovered — prefer text-math chunks / de-rank image-placeholder defs, and avoid truncation. See **Definition Recovery — further implementations** below. | [spec](docs/superpowers/specs/2026-06-16-tutor-definition-recovery-design.md) |
| **Tutor render + citation pendings (#1 formal-statement markdown, #2 reference numbering, #3 `[N]` hyperlinks)** — three live bugs in tutor output. (#2/#3) Root cause: the model self-assigns `[N]` numbers, giving one chunkId multiple indexes + emitting citations never referenced inline → dup/orphan/non-contiguous numbering. Fix: `_canonicalize_citations` in `_convert_to_tutor_answer` — dedup-by-chunkId (first-seen wins) + orphan-prune + contiguous-renumber, rewriting `[N]` in `text` AND `aspects` in sync. | 🟢 **SHIPPED + DATA-LAYER LIVE-VERIFIED (`f38441a`, 2026-06-17).** Fix built in an isolated worktree via Ollama (`glm-5.1`), reviewed APPROVED (`deepseek-v4-pro`, proved test fails pre-fix + ran edge cases), brought to main. Live SSE re-verify on a fresh "strict stationarity" answer: inline `[1,2,3]` == citations `[1,2,3]`, **no dup chunks, every marker matched both ways**, formal-statement blockquote + KaTeX `$$` render (#1 ✅). Backend 108 + frontend 18 green. The earlier "Failed to generate an answer" blocker is **moot on this branch** (drafts go through `_loads_tolerant_json_object`). **REMAINING:** (a) 🟠 **browser pixel/click certification on :5175 NOT finished** — interrupted mid-generation 2026-06-17; confirm KaTeX actually paints, no raw `>` leak, and clicking a `[N]` pill opens Sources + scrolls to `#cite-N`; (b) `finishing-a-development-branch` + clean up the `fix/citation-numbering-isolated` worktree. | [spec](docs/superpowers/specs/2026-06-17-tutor-render-and-citation-pendings-design.md) · [plan](docs/superpowers/plans/2026-06-17-tutor-render-and-citation-pendings.md) |
| **⚠️ INCIDENT 2026-06-17 — `git reset --hard` data loss (recovered)** — an Ollama implementer dispatched via `opencode run --dangerously-skip-permissions` ran `git reset --hard HEAD` despite a textual no-git constraint, wiping ALL uncommitted work in the main checkout. Recovered the bulk from the intact `feat/tutor-definition-recovery-fixes` worktree (snapshot `79b4c9f`), restored into main (`d416c16`). Encoded prevention as **rule 0 (dispatch isolation)** in the banner at the top of this file + memory `isolate-opencode-implementers-worktree`. | 🟡 **RECOVERED + HARDENED.** Caveat: `deep_tutor.py`'s recovery came from that worktree, which was a *thinner cut* there than the wiped main — any `deep_tutor.py`-only uncommitted refinements in main beyond the worktree's state are not recovered (forensic captures saved at `/tmp/incident-recovery-2026-06-17/`). Verify `deep_tutor.py` is the intended state next session. | — |

#### Definition Recovery — further implementations (next session)

Insights from the 2026-06-16 end-to-end live verify, as actionable build items. The core architecture (dedicated retrieval → verbatim extract → fidelity gate → PURE-CODE-built `formal_statements`) is proven and merged; these refine quality. Build each via the Ollama agent layer (`tools/ollama_agents/`), TDD, review + commit per task.

**DR-8a — Fix statement truncation.** Live answer cut mid-word ("…is said to be str"). Localise: is it the extract (`_extract_verbatim` `max_completion_tokens=400` too low, or the model stopping at the OCR image token), the source chunk itself truncated, or a render cap? Files: `src/services/chat/agents/definition_recovery.py` (`_extract_verbatim`), `_render_formal_statements` in `deep_tutor.py`. Add a test with a long multi-sentence definition asserting the full statement round-trips.

**DR-8b — Prefer clean text definitions over OCR-image ones.** The pipeline chose pesaran "Definition 15" (equations dropped to `![image](…gif)` placeholders) over the clean text def in `das ch09 §9.2.1.1`. Add a candidate-scoring step in `_recover_one`: penalise/skip chunks whose definition span is mostly image-placeholder math (`!\[image\]\(.*\)`); prefer chunks with inline/`$$` LaTeX or clean prose. Strip image-placeholder tokens BEFORE the fidelity-recall check (they dilute token-recall). Consider evaluating the top 2-3 candidates and keeping the highest-quality verbatim. Files: `definition_recovery.py` (`_recover_one`, candidate loop).

**DR-8c — Gap concepts must include the specific forms.** The direct test used explicit concepts `["strict stationarity","weak stationarity"]` and recovered BOTH cleanly; the full pipeline's `detect_definition_gaps` produced different/broader concepts and recovered one (truncated). Ensure `detect_definition_gaps` (or the concept list it receives) surfaces the named forms ("strict", "weak", "covariance") as distinct gap concepts so each form is recovered + rendered. Files: `definition_gaps.py`, and how `concepts` are passed at the `_recover_definitions_block` call site in `deep_tutor.py`.

**DR-8d — Chain to formula recovery for image-math definitions.** When the best definition's equations are OCR-dropped to images, that's `formula_recovery` territory (vision reads the equation off the figure). Consider chaining: definition recovery supplies the verbatim def TEXT, formula recovery fills its dropped `$$equations$$`. Files: `definition_recovery.py` + reuse `formula_recovery.recover_formulas`.

**DR-5 — Frontend structured render.** Render `formal_statements[]` as labelled `TutorFormalDef` blocks (kind/label heading + KaTeX `statement` + `[N]`/🌐 cite) in `web/src/components/views/TutorView.tsx` / `web/src/lib/mapConversationMessages.ts`; add `TutorFormalDef` to `web/src/types.ts`; fall back to legacy `formal_statement` string when empty. The markdown path already surfaces them, so this is polish + a render test (`MessageThread.test.tsx`).

**DR-6 — Docs + modal lockstep.** New feature doc `docs/services/chat-features/58-definition-recovery.md`; add the `TUTOR_DEEP_DEFINITIONS` env row + a "Definition recovery" node to the mermaid in `36-deep-tutor.md`; add the node parallel to retrieval in `web/src/data/tutorPipeline.ts` + `web/src/components/PipelineDiagram.tsx` (+ test); update `docs/system/invariants.md`, `docs/system/changelog.md`, and HTML `docs/common ground/Elements/modes/tutor.html`. (The tutor (i) modal still shows the OLD "only when a numbered theorem exists" formal-statement text — fix here.)



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
