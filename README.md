# 📚 statrag — RAG over Statistical Textbooks

[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF.svg?logo=vite&logoColor=white)](https://vitejs.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Qdrant](https://img.shields.io/badge/Qdrant-1.12-DC382D.svg?logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![OpenAI](https://img.shields.io/badge/OpenAI-embeddings%20%2B%20chat-412991.svg?logo=openai&logoColor=white)](https://openai.com/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-v4--pro-4D6BFE.svg)](https://www.deepseek.com/)
[![Groq](https://img.shields.io/badge/Groq-Llama%204%20%2B%20gpt--oss-F55036.svg)](https://groq.com/)
[![LangChain](https://img.shields.io/badge/LangChain-LangGraph-1C3C3C.svg?logo=langchain&logoColor=white)](https://www.langchain.com/)
[![KaTeX](https://img.shields.io/badge/KaTeX-math%20render-329F75.svg)](https://katex.org/)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![SSE](https://img.shields.io/badge/SSE-streaming-FF6B6B.svg)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
[![Tests](https://img.shields.io/badge/tests-488%20backend-4CAF50.svg)](src/services/chat/tests/)
[![Status](https://img.shields.io/badge/status-WIP-orange.svg)](#-status)

> A **local-first, multi-mode study companion** that turns a personal library of statistics, econometrics, causal-inference, ML, and quant-finance textbooks into a tutor that *teaches* — every claim grounded, every citation clickable, every figure pertinence-judged.

## ⚠️ Status

> [!WARNING]
> **Ongoing project — NOT complete.** Most surface area wired but only **Tutor mode** is end-to-end working today. The other 10 modes exist as scaffolding + route handlers; their pipelines are stubs, partial, or unreviewed. Treat the rest as a roadmap.

---

## 🎯 What Makes It Different

| Capability | What statrag does | Why it matters |
|---|---|---|
| **Hybrid retrieval** | Dense (OpenAI 3072d) **+** BM25 sparse, fused server-side by Qdrant native RRF | One round-trip, no client-side rank drift |
| **9-stage tutor pipeline** | Query planner → density rerank → author diversity → coverage check → figure judge → synthesis plan → structured draft | Textbook-grade answers, not chunk dumps |
| **6-aspect schema** | `TL;DR · Definition · Formal Statement · Example & Intuition · Applications · Further Reading` | Forces depth; no skimping |
| **Verbatim formal statements** | If source has a numbered theorem → blockquote it. If not → empty (heading hidden) | Zero invented math |
| **Per-claim citations** | Every `[N]` marker has a matching citation; reconciler synthesizes missing ones in marker order | No orphan refs, no renumbering bugs |
| **Image judge** | Two-tier (caption → vision) pertinence judge; up to 3 figures injected inline at the best-scoring aspect | Figures land *where they belong* |
| **Detached, resumable SSE runs** | Background `asyncio.Task` per conversation; close tab → generation keeps running → reopen → resume from last `seq` | Production-grade chat lifecycle |
| **Prompt schema invariant** | Every prompt XML-tagged (`<role>` / `<context>` / `<task>` + addenda); enforced by audit test | Small models (Llama 4 Scout, gpt-oss) don't silently break |
| **Chinese-wall architecture** | `core` imports nothing; `tasks` and `services` import only `core`; services never cross | New feature = new folder, not refactor |

---

## 🧠 Tutor Mode Pipeline (the one mode that works end-to-end)

> This graph describes **Tutor mode only**, not the whole project. It mirrors `web/src/data/tutorPipeline.ts` (the canonical source surfaced in the in-app "About this pipeline" modal) and the stage sequence in `src/services/chat/agents/deep_tutor.py::run_deep_tutor`.

```mermaid
flowchart TD
    accTitle: Tutor Mode Pipeline
    accDescr: Vertical chain from user question through query planning, hybrid retrieval, density rerank with adjacent sections, author diversity, coverage check (with re-query loop), figure judge, planner, drafting workflow, draft, vision explain, and answer.

    Q["❓ Question"]
    EX["🧠 Query planner<br/><sub>concepts · queries · facets</sub>"]
    RE["🔀 Hybrid retrieval ×N<br/><sub>dense + BM25 → RRF</sub>"]
    RR["📏 Density select + rerank<br/>+ adjacent sections<br/><sub>cross-encoder gate</sub>"]
    DV["👥 Author diversity<br/><sub>round-robin authors</sub>"]
    CC["✅ Coverage check<br/><sub>facets vs sources<br/>re-query cap 1</sub>"]
    IJ["🖼️ Figure judge (T1)<br/><sub>caption-level pertinence</sub>"]
    PL["📐 Planner<br/><sub>thesis · author contrasts<br/>worker tasks</sub>"]
    WF["🔧 Drafting workflow<br/><sub>single · orchestrator · organize</sub>"]
    DR["✍️ Draft / synthesis<br/><sub>6-aspect structured output</sub>"]
    VE["👁️ Vision explain<br/><sub>per placed figure</sub>"]
    OUT["📖 Answer<br/><sub>streamed via SSE</sub>"]

    Q --> EX --> RE --> RR --> DV --> CC
    CC -.->|missing facet,<br/>cap 1| RE
    CC --> IJ --> PL --> WF --> DR --> VE --> OUT

    classDef io   fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#7c2d12
    classDef llm  fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#4c1d95
    classDef data fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0c4a6e
    classDef img  fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d
    classDef done fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d

    class Q io
    class EX,PL,DR,VE llm
    class RE,RR,DV,CC,WF data
    class IJ img
    class OUT done
```

**Node roles** (matches the in-app modal — each LLM node is model-overridable per stage):

| Stage | Default model | Locked? |
|---|---|:---:|
| Query planner | `gpt-5.4-nano-2026-03-17` | swappable |
| Hybrid retrieval | `text-embedding-3-large` + RRF | locked |
| Density + rerank + adjacent | cross-encoder | locked |
| Author diversity | (deterministic) | locked |
| Coverage check | facet re-query | locked |
| Figure judge (T1) | `gpt-5.4-nano-2026-03-17` | swappable |
| Planner | `gpt-5.4-nano-2026-03-17` | swappable |
| Drafting workflow | single / orchestrator / organize | swappable |
| Draft / synthesis | follows picker (default nano; `deepseek-v4-pro` for organize) | swappable |
| Vision explain | `gpt-4o-mini` | swappable |

---

## 🧩 Chat Modes

| Mode | Slug | Status | Intended capability |
|---|---|:---:|---|
| **Tutor** | `tutor` | ✅ working | Deep multi-stage tutor (the whole pipeline above) |
| Compare | `compare` | 🚧 stub | Side-by-side concept / method / author comparison |
| Figures | `figures` | 🚧 stub | Figure-first retrieval and explanation |
| Quiz | `quiz` | 🚧 stub | Question generation per section / chapter |
| Navigate | `navigate` | 🚧 stub | TOC / structural browsing across books |
| Prereqs | `prereqs` | 🚧 stub | Prerequisite-concept DAG for a topic |
| Annotate | `annotate` | 🚧 stub | Inline annotation of a passage |
| Research | `research` | 🚧 stub | Open-ended research synthesis |
| Math | `math` | 🚧 stub | Equation / derivation focused answers |
| Path | `path` | 🚧 stub | Learning-path suggestion |
| Roadmap | `roadmap` | 🚧 stub | Multi-step study roadmap with milestones |

Use `mode: "tutor"` in `/api/chat` until the rest is hardened.

---

## 🏗️ Stack

| Layer | Tech |
|---|---|
| **Vector DB** | Qdrant 1.12.4 — per-field collections (`<field>_textbooks` + `<field>_images`) |
| **Embeddings** | OpenAI `text-embedding-3-large` (3072d, dense + caption) |
| **Sparse** | Qdrant native BM25 via `fastembed` |
| **Chat LLMs** | OpenAI (`gpt-5.4-nano`, `gpt-5.4`), DeepSeek (`v4-pro`), Groq (`llama-4-scout`, `gpt-oss-120b/20b`) |
| **Backend** | Python 3.12 · FastAPI · sse-starlette · LangChain / LangGraph · Pydantic v2 |
| **Frontend** | React 18 · Vite 5 · TypeScript (strict) · KaTeX · hand-rolled markdown |
| **Storage** | SQLite (conversations, prefs) · Qdrant snapshots (auto-backup) |
| **Ops** | Docker Compose · multi-stage builds · dev + prod profiles |

---

## 🚀 Quick Start

```bash
# 1. clone + venv
git clone https://github.com/IohanFaustino/statrag.git && cd statrag
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 2. secrets
cp .env.example .env
# fill OPENAI_API_KEY (required); DEEPSEEK_API_KEY / GROQ_API_KEY optional

# 3. Qdrant (empty)
docker compose -f ops/docker/docker-compose.yml up -d

# 4. frontend deps
cd web && npm install && cd ..

# 5. ingest at least one book (raw OCR sources NOT shipped)
python -m src.ingestion.pipeline --book <slug> --chapter chNN

# 6. dev stack — backend :8766 + frontend :5175
./scripts/dev.sh
```

Open **<http://localhost:5175>**.

---

## 📥 Ingest Your Own Books

The repo ships **code only** — no data, no Qdrant points, no `.env`. Full operational guide: **[`docs/tasks/ingestion.md`](docs/tasks/ingestion.md)**. Summary:

```bash
# locate chapter boundaries
grep -n "^# \|^## [0-9]\|^### [0-9]\+\.1\s" /path/to/book.md | head -40

# preview (1 LLM call, no manifest write)
.venv/bin/python -m src.ingestion.pipeline \
  --book <slug> --chapter ch01 --limit-sections 1 --force

# full ingest
.venv/bin/python -m src.ingestion.pipeline --book <slug>
```

A `rag-add-book` Claude Code skill automates steps 1–5 with three confirmation gates (yaml → preview → full).

---

## 🔌 Ports

| Profile | Frontend | Backend | Qdrant |
|---|:---:|:---:|:---:|
| dev (`./scripts/dev.sh`) | **5175** | **8766** | 6333 |
| prod (`docker compose --profile prod up`) | 5173 | 8765 | 6333 |

Qdrant dashboard: <http://localhost:6333/dashboard>.

---

## 📊 Numbers (live)

- **26** books indexed across **6** field collections
- **8,083** image points (30× growth from first pass)
- **488** backend tests + frontend test suite
- **50+** per-feature deep-dive docs ([`docs/services/chat-features/`](docs/services/chat-features/))
- **14** API routes + `GET /api/figures` (whitelisted file serving)

---

## 🔒 Security Notes (Self-Hosting)

- `.env` git-ignored. `.env.example` lists required keys.
- CORS = `allow_origins=["*"]` in `src/services/chat/api.py` for dev. **Restrict before exposing.**
- `/api/figures` whitelists local FS roots — edit `_FIGURE_ROOTS` for your machine.

---

## 📚 Docs

| Doc | Purpose |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Architecture + Chinese wall + commands |
| [`docs/system/architecture.md`](docs/system/architecture.md) | 5-stage ingestion + retrieval |
| [`docs/system/invariants.md`](docs/system/invariants.md) | 28 invariants verified per commit |
| [`docs/services/chat.md`](docs/services/chat.md) | SSE backbone + detached runs |
| [`docs/services/frontend.md`](docs/services/frontend.md) | React SPA + TutorView contract |
| [`docs/services/chat-features/`](docs/services/chat-features/) | Per-feature deep-dives (50+) |
| [`docs/tasks/ingestion.md`](docs/tasks/ingestion.md) | Add-a-book recipe |

---

## 📝 License

Personal research project. No license granted by default — contact author.
