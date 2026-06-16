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
| **Formula recovery + global cache** — gap-triggered second-RAG: when a concept's defining equation was OCR-dropped to an image, gpt-4o **vision reads the equation off the figure** (`search_figures`+`inspect_figure` w/ transcription instruction), text re-query fallback, fed into the synth as `<recovered_equations>` (used verbatim); recovered equations cached globally in a `formula_cache` Qdrant collection for consistency/cost. Lightweight `asyncio.gather` (no deepagents). | ✅ **shipped** (branch `feat/ow-harness-pland`) — modules `formula_gaps.py`/`formula_cache.py`/`formula_recovery.py`; wired into `run_orchestrator_workers`; modal + 36 mermaid + invariant 37 + doc 56 lockstep done. Pending: live manual verify on :5175 (real gpt-4o $). | [spec](docs/superpowers/specs/2026-06-04-formula-recovery-and-cache-design.md) · [plan](docs/superpowers/plans/2026-06-04-formula-recovery-and-cache.md) |
| **Deep-synth formulas wrong + Bias/Variance missing formulas** — superseded by the narrative rebuild below; the orchestrator-deep path and per-author workers are deleted. Formula recovery is rewired to the single narrative draft call. Re-verify with a bias-variance query on :5175 in T8 (live verify). | ✅ **superseded by tutor narrative rebuild (2026-06-11)** | [doc 57](docs/services/chat-features/57-tutor-narrative.md) |
| **Plan D — productionize L3b** (deepagents) + lean-structured follow-on | ✅ shipped (2026-06-04) — then superseded by the narrative rebuild (2026-06-11); OW/deepagents synthesis deleted. | [doc 56](docs/services/chat-features/56-deep-synthesis-l3b.md) |
| **Tutor narrative rebuild** — collapsed 7 synthesis variants → 1 woven-narrative draft; seam validator (`seams.py`, pure code); bounded non-streamed redraft (composite acceptance); thesis injection; formula recovery rewired to the single draft. 8 tasks via subagent-driven-development (impl + spec + quality review each), opus whole-branch review READY. **Live-verified on :5175** (bias-variance: thesis-anchored openers, `### Bias` $$ rendered, formalize-drop on no-theorem, `quality={seam_continuity:1.0,lang_ok:1.0,thesis_adherence:1.0}` persisted, 0 console errors, modal=single Narrative-draft path). `rag-verify`: only pre-existing `page_from=-1`. | ✅ **MERGED into `feat/component-equation-enforcement` 2026-06-11 (fast-forward, 24 commits @ 29b0171); 850 backend tests green on merged result.** Minor follow-up: modal "Narrative draft" node could note the seam-validate step (folded today). | [doc 57](docs/services/chat-features/57-tutor-narrative.md) · [spec](docs/superpowers/specs/2026-06-11-tutor-narrative-rebuild-design.md) · [plan](docs/superpowers/plans/2026-06-11-tutor-narrative-rebuild.md) |
| **Q&A storytelling + Wikipedia rebuild** — flat pipeline `scope → retrieve(corpus ∥ wiki) → write → bind(PURE CODE) → verify` emitting `QAStoryAnswer{intro, deepening, conclusion}` in a **storytelling voice** (intro 1 / deepening ≤3 / conclusion 1 paragraph, no headings), **anti-tutor by construction** (3 fixed string fields, writer schema has no citation field). Wikipedia augments corpus (corpus-primary; 1 lookup on `target_gap` + ≤2 on scope `wiki_terms`, `asyncio.gather`); pure-code `qa_bind` rewrites `[[eid]]`→`[n]` + builds verbatim `StoryCitation` 📕 corpus / 🌐 wiki (invalid token → strip marker, keep prose). Shared `src/services/chat/research.py` extracted from Extension (Extension byte-identical). Legacy `QAAnswer` convs keep old card via discriminator. Hard tutor-isolation (ast-grep test). **Supersedes the deepagent-roster design** (`scope→gate→orchestrator±analysts→organize→checker loop`) — that roster was cut as YAGNI per fable creative-advisor. | ✅ **COMPLETE — merged into `feat/component-equation-enforcement` 2026-06-11 (ff `81c5b36..a8d2902`, 21 commits). 904 chat / 935 backend / 288 frontend green, tsc clean. Live-verified on :5175 (3-act narrative, KaTeX, real 🌐 Chebyshev wiki URL, bind=pure-code modal node, fail-open degradation, reload persistence, 0 console errors). rag-verify: only pre-existing `page_from=-1`.** Built via orchestrator_Agent (iohan-powers) + fable creative-advisor; 10 TDD tasks subagent-driven w/ sonnet. Minor: nano occasionally boxes a stray `\mu` inline (math_blocks formula clean). | [spec](docs/superpowers/specs/2026-06-11-qa-story-wiki-design.md) · [plan](docs/superpowers/plans/2026-06-11-qa-story-wiki.md) · [doc 51](docs/services/chat-features/51-qa-mode.md) · superseded: [old spec](docs/superpowers/specs/2026-06-05-qa-deepagent-design.md) |
| **Extension mode** — `extension` chat mode (deepagents topology C; corpus+Wikipedia footnote augmentation; styled-HTML ZIP export). **✅ MERGED into `feat/component-equation-enforcement` 2026-06-10** (was branch `worktree-feat+extension-mode`; 875 backend / 238 frontend tests green, tsc clean). 2026-06-10 polish batch (changelog top entry): QA black-screen guard ported + single `StructuredErrorBoundary` in MessageThread; digest markdown rendering (bold/italic, `[^n]` strip, marker dedupe) + legacy math-delimiter normalization on render; runner stamps authoritative `digest.book`/`digest.chapter` (honest narrowed label, e.g. `ch07 · 7.4–7.5`) + section-number word-boundary subtopic matching; lost answer for conv `9d9985d3…` RECOVERED into that worktree's `data/chat.db` via `ops/scripts/backfill_extension_conv.py` (20 points/20 footnotes, live-verified); orchestrator now directs parallel analyst task fan-out. **NOTE: extension conversations still live ONLY in the worktree's own `data/chat.db`** — run `./scripts/dev.sh` FROM `.claude/worktrees/feat+extension-mode` to see them (each checkout has its own chat.db). **Remaining follow-ups:** (a) live timing run to confirm parallel-analyst speedup (~17min baseline); (b) language drift (Polish) in long runs — prompt-level, unresolved; (c) ZIP filename embeds `·`/`–` from chapter label (cosmetic); (d) optional: migrate worktree chat.db convs into main checkout db. | ✅ **merged 2026-06-10; superseded by Extension v2 below** | [spec](docs/superpowers/specs/2026-06-09-extension-mode-design.md) · [plan](docs/superpowers/plans/2026-06-09-extension-mode.md) · [doc 54](docs/services/chat-features/54-extension-mode.md) |
| **Extension v2 — story timeline + curiosity boxes (REBUILD)** — deterministic async pipeline replacing deepagents core: `scope → fetch → storyteller×N → story_editor → subject_miner×take → researcher×subject (PURE CODE) → curiosity_writer×take → citation_binder (PURE CODE, verbatim payload citations) → judge (one retry) → StoryDigest`. `StoryDigestCard` (timeline rail, per-take curiosity toggle, corpus 📕 + wikipedia 🌐 chips, multi-paragraph justified KaTeX prose, narrative through-line across takes, plain-text headings). Legacy `ExtensionDigest` convs keep old card. ZIP export: per-take numbered footnotes, clickable wiki links, sanitized filename (`hansen-ch07-7.4-7.5-extended.zip`). **✅ COMPLETE — merged into `feat/component-equation-enforcement` 2026-06-10/11.** All 15 tasks + post-verify batch (T-A multi-paragraph prompts + research diagnostics, T-B card paragraphs/heading-math/full-bar-toggle/rail alignment, T-C filename sanitization end-to-end + package-logger handler) done via subagent-driven-development w/ per-task spec+quality reviews + final opus whole-impl review (READY TO MERGE). Live-verified on :5175: corpus+wiki chips render, wiki link opens article, no black-screen, ZIP valid, reload persistence, zero console errors. Gates: ~896 backend / 261 frontend tests green, tsc clean. rag-verify: only pre-existing `page_from=-1` ingestion-era violations (murphy/peck/neal/stock_watson/cunningham/wooldridge), unrelated. **NOTE: extension convs live in each checkout's own `data/chat.db`** (v2 verify convs in `.claude/worktrees/extension-v2/data/chat.db`). Known minor: occasional model puts prose inside `$...$` (nano content quality); wiki citation density varies per run (3–4 per digest). | ✅ **COMPLETE — merged 2026-06-10/11** | [spec](docs/superpowers/specs/2026-06-10-extension-v2-story-curiosity-design.md) · [plan](docs/superpowers/plans/2026-06-10-extension-v2-story-curiosity.md) · [doc 54](docs/services/chat-features/54-extension-mode.md) |
| **Facilitate story remake** — single-section narrative pipeline replacing the chapter-loop design: `parse → fetch ONE section (closest-match+confirm) → map (concept anchors) → write story (hook/movements/takeaway, verbatim formal statements unpacked) → bind (PURE CODE, provenance+citations verbatim) → verify (PURE CODE, statement fidelity token-recall)`. `FacilitateStoryCard` + `ConceptChat` side panel (`POST /api/concept/explore`, stateless). `FacilitateDigest` kept for legacy stored convs. 9 tasks via subagent-driven-development + creative-advisor. All 9 tasks complete + docs lockstep done (T9). **Gates: 300 frontend tests green, tsc clean.** Pending: live verify on :5175 + rag-verify + merge. | ✅ **COMPLETE on branch `feat/facilitate-story-remake` (2026-06-12); docs/modal lockstep done (T9). Live verify + merge pending.** | [spec](docs/superpowers/specs/2026-06-12-facilitate-story-remake-design.md) · [plan](docs/superpowers/plans/2026-06-12-facilitate-story-remake.md) · [doc 53](docs/services/chat-features/53-facilitate-concept-map.md) |
| **Ollama agent-delegation layer (Python)** — PRIMARY ACTIVE TASK (2026-06-16). Build a Python harness IN THIS REPO (new folder, e.g. `tools/ollama_agents/`) that delegates a task to an **Ollama-cloud-brained agent** the same way the Claude Code `Agent` tool delegates to a Claude subagent. Ollama = the agent brain/executor; the harness = the loop (system prompt + tool schemas read_file/write_file/edit_file/run + tool-exec loop + transcript). Must reproduce, step-by-step, what a sonnet subagent does here (TDD task → reads files → writes code → runs tests → commits). **Batteries of tests** until parity. Integrate with agent frameworks (VoltAgent — note: TS, proven at `/tmp/volt-ollama` w/ `@ai-sdk/openai-compatible@1`; Python option = langchain `create_agent` / deepagents skills) + superpowers skills. Ollama API via Python: OpenAI SDK pointed at `https://ollama.com/v1` (key in env; MCP key `265eb1d8…`, settings key `7bed006e…`). **Why this exists:** Claude Code subagents CANNOT be brained on `ollama-cloud/*` (errors instantly, 0 tokens — verified). This Python layer is the workaround so real Ollama agents can execute tasks. | 🟢 **CORE BUILT + LIVE-VERIFIED (`c23c9f0`, 2026-06-16).** `tools/ollama_agents/` — `delegate(task,model,root)` runs an Ollama agent via native `/api/chat` function-calling (read/write/edit/run tools + loop). Batteries: 8 tool + 4 loop (mocked) green; **live parity** proven (`qwen3-coder-next` took a TDD task to green in 4 steps `[write_file,write_file,run]`). Auth gotcha documented: native endpoint not `/v1`; `.env`-first matched key+host; key contains a `.` (regex-truncation = silent 401). **Remaining:** (a) framework/skills integration — VoltAgent is TS (proven `/tmp/volt-ollama`); Python equivalent = langchain `create_agent`/deepagents (both installed); SKILL.md capability loading; (b) per-task reviewer parity (spec+quality reviewer agents); (c) USE it to drive the tutor formal-defs/wiki feature impl. | [README](tools/ollama_agents/README.md) |
| **Tutor: verbatim formal definitions + promoted Wikipedia** — Part A: brand-new tutor-only `TutorFormalDef` list (multi verbatim defs, relaxed gate — strict+weak stationarity each verbatim; NO reuse of other modes' classes). Part B: Wikipedia anchor + interleave (promote from augment-only/trailing). 7 TDD tasks. Spec + plan written & committed; impl NOT started (paused to build the Ollama layer first, per user — the feature is to be implemented via that Ollama agent layer). Base `96fcae9` on `feat/component-equation-enforcement`. Prior-session Wikipedia-cited-source base checkpointed at `3ef3e31`. Live gate: stationarity query on :5175. | 🟡 **BACKEND DONE (Tasks 1–5, all via Ollama agents, reviewed+committed `29dc332`→`5b489e3`, +contract reconcile `66c4019`; full chat suite green). LIVE-VERIFIED on :5175 (stationarity query, 0 console errors): ✅ Part B Wikipedia WORKS — interleaved at #3 (Stationary process, anchors the definition `[3]`) and #6 (Unit root test), not trailing; ADF/KPSS covered. ❌ Part A NOT surfacing — no "Formal statement" section; gpt-5.4-nano PARAPHRASED strict/weak stationarity into the Definition beat instead of populating the new `formal_statements` list verbatim (the field is optional/empty-default, nano takes the easy path). Machinery (schema+render+prompt) is correct but it's true-by-instruction and nano ignores it. ALSO: Hansen (user's cited source for strict/weak) didn't rank top-10 here (got spark_ts/atwan/cerqueira/wooldridge/wiki). **Part A SUPERSEDED by Definition Recovery design (below)** — the true-by-instruction approach can't work (nano won't populate; def not even retrieved). Part B (wiki) stays shipped. Still pending regardless: Task 6 frontend structured render; Task 7 docs/modal lockstep. | [spec](docs/superpowers/specs/2026-06-16-tutor-formal-defs-and-wiki-promote-design.md) · [plan](docs/superpowers/plans/2026-06-16-tutor-formal-defs-and-wiki-promote.md) |
| **Tutor: Definition Recovery (verbatim formal defs as PREMIUM info)** — ACTIVE design (2026-06-16). Root-cause of the missing formal defs: (1) the formal definition (e.g. Hansen strict/weak stationarity) is never RETRIEVED to top-k by the general query, and (2) the draft paraphrases it. Fix mirrors the live `formula_recovery` trio: new `definition_gaps.py`/`definition_recovery.py`/`definition_cache.py` — gap-detect → DEDICATED definition-shaped retrieval per concept (surfaces Hansen) → LLM-extract verbatim span + PURE-CODE token-recall fidelity gate → Qdrant `definition_cache` → **CODE builds `formal_statements[]` (true-by-construction; draft weaves prose, can't paraphrase)** → override `answer.formal_statements`. Env `TUTOR_DEEP_DEFINITIONS`. Reuses TutorFormalDef schema (`29dc332`) + render (`507e3b3`). To be implemented via the Ollama agent layer (`tools/ollama_agents/`). Live gate: stationarity → verbatim strict+weak shown. | 🟢 **BACKEND BUILT + CORE VERIFIED (2026-06-16).** Phases DR-1..4 all via Ollama agents (`e840555`→`8b28d05`) + import fix (`28dfb51`); 30 DR unit tests + full chat suite green. **DIRECT CORPUS VERIFY:** `recover_definitions(["strict stationarity","weak stationarity"])` returns 2 VERBATIM defs from `das ch09 §9.2.1.1` ("A time series process y_t is strictly stationary or strongly stationary if the joint probability distribution…depends only on the lag length…" + "…weakly stationary or covariance stationary if its first- and second-order moments are unaffected by a change in time origin") — premium info the general retrieval never surfaced. Bug found+fixed: `apply_structured_output` import was from `llm.router` not `llm.structured` (mocked tests had patched past it → silent 0 recovered); regression test added. **REMAINING:** DR-5 frontend structured `formal_statements[]` render (markdown path already surfaces them); DR-6 docs/modal lockstep + new doc 58; DR-7 full end-to-end UI confirm on :5175 (browser renderer was unresponsive this session — retry). | [spec](docs/superpowers/specs/2026-06-16-tutor-definition-recovery-design.md) |



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
