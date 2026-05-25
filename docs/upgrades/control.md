# Chat Upgrade — Control Tracker

> **Restoration doc.** Conversation will be cleared after this checkpoint. Any future Claude session must read this file first to resume. Multi-session task: turn `abstract.md` into buildable, tested chat RAG system over indexed statistical textbooks.

---

## 0. Aim (verbatim from user)

> "Prepare series of documents to build efficient RAG chat system."

Concrete deliverable: 11 chat modes from `docs/upgrades/abstract.md`, mounted on existing hybrid retrieval (dense `text-embedding-3-large` + sparse `bm25` over per-field Qdrant collections), with tested prompt + retrieval + relevance quality. Existing code lives under `src/services/chat/` and `src/services/retrieval/`.

---

## 0b. Stack (frozen — do not change without user confirmation)

- Vector DB: Qdrant 1.12.4 (Docker, `localhost:6333`)
- Embeddings: `text-embedding-3-large` (OpenAI, 3072d)
- Sparse: Qdrant native BM25 via `fastembed`
- LLM default: `gpt-5.4-nano-2026-03-17`; alt `deepseek-v4-pro`
- Chunking: 1 section = 1 chunk, split at 8000 tok (`cl100k_base`)
- Python 3.12 in `.venv`
- Frontend: React 18 + Vite + TS at `web/`
- Backend: FastAPI at `src/services/chat/api.py`
- Persistence: SQLite at `data/chat.db`

## 0c. Common commands

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
docker compose -f ops/docker/docker-compose.yml up -d            # Qdrant
.venv/bin/python -m pytest src/services/chat/tests/ -v           # 61 tests
./scripts/dev.sh                                                 # backend :8765 + vite :5173
.venv/bin/python -m src.services.retrieval.cli "<q>" --book <slug>
python ops/scripts/render_state.py                               # regen state.md
```

---

## 1. Sources (input material)

All paths under `/home/iohan/Documents/Converters/Books/Process/Files/Output/AI/`.

| Code | Title | Author | Year | Path suffix |
|------|-------|--------|------|-------------|
| A | Building AI Agents with LLMs, RAG, and Knowledge Graphs | — | — | `Building AI Agents with LLMs, RAG, and Knowledge/Building AI Agents with LLMs, RAG, and Knowledge.md` |
| B | Building Natural Language and LLM Pipelines | Funderburk | Packt 2025 | `Building Natural Language and LLM Pipelines_ ... 502c06ed872898cf88f18f9c142647a5 ... .md` |
| C | AI Agents in Action | Lanham | Manning 2025 | `AI Agents in Action -- Micheal Lanham ... bc2eefa147a03f02caac7a526302e940 ... .md` |
| P | RAG with Python Cookbook | Polzer | O'Reilly 2026 | `RAG with Python Cookbook_ ... 115885543 libgen.li/...md` |
| — | AI Engineering in Practice | — | — | **SKIPPED — file empty (cover-only)** |

Chapter counts: A=11, B=10, C=11, P=11. All 43 chapters synopsised.

---

## 2. Outputs (file map)

```
docs/upgrades/
├── abstract.md                      # input — 11 services design
├── control.md                       # this file
├── Chat/
│   ├── synopsis/
│   │   ├── README.md                # index of 43 chapters
│   │   ├── A01..A11_*.md            # Book A — 11 files
│   │   ├── B01..B10_*.md            # Book B — 10 files
│   │   ├── C01..C11_*.md            # Book C — 11 files
│   │   └── P01..P11_*.md            # Book P — 11 files
│   ├── key_aspects_map.md           # need → chapter mapping (8 sections)
│   ├── build_instructions.md        # ← NEXT (step 3)
│   ├── implementation_plan.md       # ← step 4
│   └── test_plan.md                 # ← step 4
└── Demo/                            # legacy demo (don't touch)
```

Status: synopsis + key_aspects_map written. build_instructions, implementation_plan, test_plan **not yet written**.

---

## 3. Steps + status

| # | Step | Status | Artifact | Done at |
|---|------|--------|----------|---------|
| 0 | Understand aim + scan sources | done | this file | 2026-05-17 |
| 1 | Synopsis per chapter all books | **done** | `Chat/synopsis/*.md` (43 + README) | 2026-05-17 |
| 2 | Map key aspects → sources | **done** | `Chat/key_aspects_map.md` (8 sections) | 2026-05-17 |
| 3 | Distill abstract → build instructions | **done** | `Chat/build_instructions.md` | 2026-05-17 |
| 4 | Implementation plan + tests | **done** | `Chat/implementation_plan.md` + `Chat/test_plan.md` | 2026-05-17 |
| 5 | Fix + solve problems from tests | pending — blocked on §9 user decisions | code under `src/services/chat/`, `src/services/retrieval/` | — |

**Current resume point: Step 5 — pending user confirmation on §9 open decisions (defaults proposed in `Chat/build_instructions.md §10`).**

---

## 4. Key findings consolidated (so step 3 starts hot)

### 4a. Highest-leverage chapters (must-mine for build instructions)

| Chapter | Why it matters |
|---------|----------------|
| **P7 — Advanced Retrieval** | Multi-query · HyDE · reranking · query decomposition · metadata filter. Direct recipes for missing Phase-2 stages. |
| **P10 — Evaluation** | Automated metrics + LLM-judge + synthetic test set generation. Direct content for `test_plan.md`. |
| **P8 — Agentic RAG** | Loop pattern: query → tool select → retrieve → assess → continue. Template for tutor follow-ups + research assistant. |
| **A6 — Advanced RAG** | Hierarchical indexing, HyDE, query routing, reranking, context enrichment, modular RAG. Conceptual depth. |
| **A5 — RAG Basics** | Chunking + embedding + eval metrics. Validates current "1 section = 1 chunk, 8000 tok split". |
| **B4 — Haystack Pipelines** | Hybrid+rerank 4-stage exactly matches needed retrieval. Vision-RAG Strategy 2 (caption-first + image-bytes gate) → Service 3/9. |
| **B8 — Hands-On Projects** | LangGraph-style state machine: clarification + worker + supervisor + approval. Template for multi-agent services. |
| **C5 — Actions / Semantic Kernel** | Function calling = retrieval-as-tool. Mix of semantic (LLM) + native (Python) functions = our pattern. |
| **C8 — Memory + Knowledge** | Knowledge (static corpus) vs memory (per-conv). Dual-namespace vector store. |
| **C9 — Prompt Flow** | Prompts as versioned code + regression eval. Required for prompt-eff test type. |
| **C10 — Reasoning + Eval** | CoT toggle per mode + self-check pass. |
| **C11 — Planning + Feedback** | Plan/check/replan loop for Service 10 (study path). |
| **B2 — LLMs Deep** | Context engineering > prompt engineering. Memory strategies (sliding / summary / vec). |
| **A3 — LLMs as Engine** | ICL + few-shot + hallucination + citation discipline. |
| **A9 — Multi-Agent** | HuggingGPT 4-step (plan → select → exec → respond) = orchestrator template for services 6/8/10. |
| **C4 — AutoGen / CrewAI** | Role-based crews + group chat. Mirror schema, don't import. |
| **P9 — Graph RAG** | Practical KG recipes — preferred over A7 for implementation of Service 6. |

### 4b. Medium-leverage

- P2 — prompt templates per task; Ollama path.
- P4 — metadata enrichment (verify payload completeness).
- P5 — embedding selection (validate large model; consider small for HyDE).
- B5 — Ragas eval + synthetic test data.
- B6 — observability (W&B or local jsonl).
- B7 — FastAPI/Docker deploy validation.
- C2 — model selection rubric.
- C7 — persona class per mode.

### 4c. Low / skip for chat phase

- A1, A2 — pre-transformer/transformer foundations (background only).
- A8 — full RL (not needed; RLHF mentioned in A3 suffices).
- A10 — Streamlit (we use React).
- A11 — strategic framing only.
- B9, B10 — future/epilogue (philosophy not blocking).
- C1, C3, C6 — agents intro / GPT-platform / behavior trees (alternatives we don't pick).
- P1, P3, P6, P11 — getting-started / loaders / vector-DB pick / Streamlit (already decided).

---

## 5. Per-service architecture decisions (carry into step 3)

Pulled from `abstract.md` + cross-referenced w/ all 43 synopses. **Triple-checked** for source coverage.

| # | Service | Architecture | Required techniques | Source synopses |
|---|---------|-------------|---------------------|----------------|
| 1 | Tutor | Single agent + memory + agentic loop | query rewrite, sliding/summary/vec memory, citation, agentic loop (bounded ≤3 tool calls) | A3, B2, C8, P8 |
| 2 | Cross-book | Single agent, dual retrieval (parallel async) | multi-query, HyDE, dedup, per-source attribution | B4, A6, P7 |
| 3 | Figure-aware | Single agent, dual-collection | caption-first vision RAG, gate to send image bytes only when score crosses τ | B4, P3 |
| 4 | Quiz | Single agent, 2-stage chain | self-check pass (Q answerable from retrieved text), ICL, repetition tracker, KaTeX | A3, B5, C10 |
| 5 | Navigator | Single agent, retrieval-only | query expansion + HyDE, structured location output, canonical ranking | A6, P7 |
| 6 | Prereq tracer | **Multi-agent** | Polzer KG recipes, entity/relation extraction, cycle detection on DAG | A7, P9, A9, B8 |
| 7 | Annotated reading | Single agent, batch parallel | noun-phrase extraction, threshold gate, multi-query | A6, B4, P7 |
| 8 | Research assistant | **Multi-agent** | claim decomposition (P7), stance classifier (SUPPORTS/CONTRADICTS/BG), synthesis | A9, B8, C4, P7 |
| 9 | Math explainer | Single agent, vision-augmented | CoT, LaTeX fidelity check, vision gate (B4 strategy 2) | B4, A6, C10 |
| 10 | Study path | **Multi-agent** (most complex) | goal decomposer, plan/feedback loop, persisted state, replanning trigger | B8, A9, C11 |
| 11 | Roadmap | Single → Multi (v2) | multi-query, structured YAML schema, decomposition, validator | A6, B5, P7 |

---

## 6. Existing code shape (target of modifications)

Layout (Chinese-wall enforced — `src/core` imports nothing; `src/services/*` imports only `src.core`):

```
src/core/                       # config, qdrant_store
src/services/retrieval/
  ├── retrievers.py             # dense + sparse + RRF fusion
  ├── chain.py                  # answer composition
  └── cli.py
src/services/chat/
  ├── api.py                    # FastAPI app, 14 routes incl. SSE /api/chat
  ├── orchestrator.py           # rewrite → retrieve → LLM stream
  ├── retrieval.py              # hybrid RRF over per-field collections
  ├── rewriter.py               # query rewrite
  ├── highlights.py             # sentence-level dense re-score for spans
  ├── books.py                  # book registry (manifest + yamls)
  ├── store.py                  # SQLite conversations + messages + prefs
  ├── schemas.py                # Pydantic models
  ├── prompts/                  # system prompts (current minimal set)
  ├── llm/                      # router.py (OpenAI + DeepSeek)
  └── tests/                    # 61/61 passing
web/                            # React + Vite + TS SPA
data/chat.db                    # SQLite (conversations, messages, prefs)
```

State as of 2026-05-17 (from `docs/services/chat.md`): backend 14 routes, 61/61 tests pass, SSE verified via curl. Frontend compiles, vite build 51 modules. Ports backend `:8765`, vite `:5173`. SSE event order: `meta` → `token`+ → `paragraph_break` / `math_block` / `figure` / `source_chip` → `sources_full` → `figures_full` → `retrieval_meta` → `done`.

**Gaps the next steps must fill:**
- Reranker stage (cross-encoder) — missing.
- HyDE / multi-query / query decomposition — missing.
- Persona/prompt set covering only 11 modes — currently 1.
- Multi-agent orchestration for services 6, 8, 10 — missing.
- Evaluation harness (Ragas-style + LLM-judge + synthetic Q/A) — missing.
- Vision gate for figure mode — missing.
- Per-conversation vector memory namespace — missing.
- Plan/checkpoint persistence for Service 10 — missing.

---

## 7. Step 3 — exact deliverable (next session starts here)

Create `docs/upgrades/Chat/build_instructions.md` with these sections (triple-checked against abstract.md + 43 synopses):

1. **Backbone restated** — query processor → hybrid retriever → reranker → context assembler → LLM → output formatter. Cite which synopsis justifies each stage.
2. **Per-mode persona template** — system prompt + few-shot + output schema + tool list per mode. 11 entries. (source: C7 + C2 + A3)
3. **Retrieval upgrades (Phase 2)** — concrete ordered list: add reranker → HyDE → multi-query → metadata filter → query decomposition. Each w/ source recipe pointer (P7).
4. **Memory architecture** — knowledge `*_textbooks` (read-only) + memory `conv_<id>` (per-conv ephemeral). Sliding/summary/vec strategy switch. (source: C8 + B2)
5. **Multi-agent shape** — LangGraph-style minimal state machine: state dict (intent, retrieval_results, draft, qc_status, citations) + nodes (clarify, retrieve, decompose, synthesize, qc, finalize). Services 6, 8, 10 instantiate variants. (source: B8 + A9 + C4)
6. **Tool-calling channel** — retrieval exposed as function the LLM can invoke; cap N calls at 3. Agentic-RAG loop. (source: C5 + P8)
7. **Vision gate** — caption-first; image bytes only if `caption_score < τ` AND `image_score ≥ τ_img`. (source: B4 strategy 2)
8. **Output schemas** — JSON/YAML/markdown per mode. Mandatory citation block: `{book, chapter, section, page_range?}`.
9. **Cost tiers** — per mode model selection (nano/pro/deepseek). Justify w/ B6 economics + C2 selection.
10. **Open decisions for user** — list anything ambiguous in abstract.md that must be confirmed before writing code.

---

## 8. Step 4 — test plan deliverables (after step 3)

Create `docs/upgrades/Chat/test_plan.md` with these test types (from user task spec):

| Type | What it verifies | Source recipe |
|------|------------------|--------------|
| **Tool integrity** | API endpoints respond, Qdrant connects, LLM responds, SSE streams cleanly | existing tests/ + B7 |
| **Retrieval relevance** | top-k contains gold chunks; context precision/recall on synthetic Q/A set | P10 + B5 + A5 |
| **Faithfulness** | answer contains only claims supported by retrieved chunks (LLM-judge) | P10 + B6 |
| **Answer relevance** | answer addresses the question (LLM-judge + cosine on gold) | P10 |
| **Prompt regression** | per-mode prompt version-diff eval over fixed eval set | C9 |
| **Citation coverage** | every claim has citation; citations point to valid sections | A3 + A5 |
| **Latency / cost** | p95 latency per mode, $/query distribution | B6 |
| **Multi-agent QC** | supervisor approval gate triggers when groundedness < τ | B8 |
| **Vision gate** | image bytes only sent when score gate justified | B4 |
| **Memory regression** | tutor remembers prior turn; vector-memory recall correctness | C8 + B2 |
| **Synthetic Q/A generation** | offline gen of test set from `data/parsed/manifest.json` sections | P10 + B5 |

Also create `Chat/implementation_plan.md` w/ ordered milestones:
1. Add reranker (1d) — single highest-ROI.
2. Add persona templates for 11 modes (2d).
3. Add HyDE + multi-query (1d).
4. Add evaluation harness + synthetic Q/A gen (2d).
5. Ship multi-agent shell for Service 6 prereq tracer (2d).
6. Ship multi-agent for Service 8 research assistant (2d).
7. Ship multi-agent for Service 10 study path (3d).
8. Vision gate + Service 3/9 (2d).
9. Per-conv memory namespace (1d).

---

## 9. Open decisions to confirm with user (before step 5)

1. Reranker model choice: `bge-reranker-v2-m3` (local, free) vs `cohere/rerank-3` (API, paid)?
2. Vision model: GPT-4o (paid) vs local LLaVA? Cost gate threshold τ?
3. Local fallback path (Ollama) — enable or defer?
4. Eval set size + cadence (10 / 50 / 200 questions; nightly vs on-PR)?
5. Multi-agent framework: roll our own state-dict machine vs use LangGraph?
6. KG persistence: in Qdrant as additional collection vs separate NetworkX/SQLite?

---

## 10. Triple-check log

Pass 1: confirmed all 43 chapters have synopsis files + README index updated. ✓
Pass 2: confirmed `key_aspects_map.md` 8 sections each cite at least one source per row; service mapping table has source codes for all 11 services. ✓
Pass 3: confirmed step 3/4 deliverables cite specific synopses; gaps in current code listed; open decisions surfaced; no orphan task. ✓

---

## 11. Session log

- 2026-05-17 (S1) — created tracker, planned outputs, started synopsis Book A + B.
- 2026-05-17 (S1) — completed synopsis A1–A11 + B1–B10, wrote `key_aspects_map.md`. Step 4 paused for more refs.
- 2026-05-17 (S2) — user added 3 books; AI Engineering in Practice empty so skipped. Wrote synopsis C1–C11 (Lanham) + P1–P11 (Polzer). Updated README + key_aspects_map. Triple-checked. **Context to be cleared after this checkpoint.**
- 2026-05-17 (S3) — Steps 3 + 4 done. Wrote `Chat/build_instructions.md` (10 sections per §7 spec), `Chat/implementation_plan.md` (9 milestones, 16 dev-days), `Chat/test_plan.md` (11 test types). Step 5 blocked on §9 open decisions; defaults proposed in build_instructions §10.
- 2026-05-17 (S4) — Re-pass requested. (1) Two rigorous passes over Step 3: verified against code (`schemas.py::ModeId`, `router.py` model IDs, `chunk_index` payload, `Figure.score` only-one-score); rewrote `build_instructions.md` aligning mode IDs (`compare/figures/navigate/prereqs/annotate/path` not `cross_book/figure_aware/…`), separating tools vs validators vs graph nodes, simplifying vision gate to single-score, expanding cost accounting w/ aux LLM hops, growing open-decisions from 8→12. (2) Loaded `architecture-designer` + `create-implementation-plan` skills; rewrote Step 4: `implementation_plan.md` now has NFRs, Mermaid architecture diagram, 6 ADRs, 10 risks w/ mitigations, 4 execution waves, self-contained milestone tickets w/ files+code+tests+acceptance, dependency graph (10 milestones, 31 pts); `test_plan.md` aligned to milestone gates w/ NFR↔test mapping, milestone↔test matrix, wave-exit gates, risk-driven extras.

---

## 12. How a fresh session resumes

1. Read `docs/upgrades/control.md` (this file).
2. Read `docs/upgrades/abstract.md` (11 services).
3. Read `docs/upgrades/Chat/synopsis/README.md` then highest-leverage chapters listed in §4a.
4. Read `docs/upgrades/Chat/key_aspects_map.md`.
5. Skim `docs/services/chat.md` for current code shape.
6. Resume at **Step 3** — write `Chat/build_instructions.md` per §7 spec.
7. Then Step 4 — write `Chat/implementation_plan.md` + `Chat/test_plan.md` per §8.
8. Then Step 5 — execute code changes.

No tool calls needed before reading these files. Do not re-summarize chapters; use existing synopses.
