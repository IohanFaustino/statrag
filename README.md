# statrag — RAG over Statistical Textbooks

## Aim

Build a **local-first, multi-mode study companion** over OCR-processed
statistics, econometrics, causal-inference, ML, and quant-finance textbooks.
The system answers user questions with grounded, citation-backed explanations
by combining hybrid retrieval (dense + BM25 over per-field Qdrant collections)
with a multi-stage tutor pipeline — query planning, density-based rerank,
author diversity, coverage check, figure judging, and a vision-aware drafting
workflow. Frontend renders the streamed answer with KaTeX math, figure
embeds, and inline citations.

> [!WARNING]
> **Status: ongoing project — NOT complete.**
> Most of the surface area is wired but only one chat mode (**Tutor**) is
> functional end-to-end today. The other 10 modes exist as scaffolding and
> route handlers but their pipelines are stubs, partial, or unreviewed.
> Treat the rest as a roadmap, not a feature list.

## Chat modes

The backend declares **11 modes** in `src/services/chat/schemas/_core.py`
(`ModeId` literal). Working state:

| Mode | Slug | Status | What it is (intended) |
|---|---|:---:|---|
| **Tutor** | `tutor` | ✅ working | Deep multi-stage tutor: concept extraction → query plan → hybrid retrieval → density + author diversity + rerank → coverage check → figure judge → drafted answer (single / orchestrator / organize workflows) → vision explain. **This is the only end-to-end working mode.** |
| Compare | `compare` | 🚧 stub | Side-by-side comparison of two concepts / methods / authors. |
| Figures | `figures` | 🚧 stub | Figure-first retrieval and explanation. |
| Quiz | `quiz` | 🚧 stub | Question generation from a section / chapter. |
| Navigate | `navigate` | 🚧 stub | Table-of-contents / structural browsing across books. |
| Prereqs | `prereqs` | 🚧 stub | Surface prerequisite concepts for a topic. |
| Annotate | `annotate` | 🚧 stub | Inline annotation of a passage or selection. |
| Research | `research` | 🚧 stub | Open-ended research synthesis across collections. |
| Math | `math` | 🚧 stub | Equation / derivation focused answers. |
| Path | `path` | 🚧 stub | Learning-path suggestion. |
| Roadmap | `roadmap` | 🚧 stub | Multi-step study roadmap with milestones. |

Use `mode: "tutor"` in any `/api/chat` request until the rest is hardened.

## Stack

- **Vector DB**: Qdrant 1.12.4 (Docker)
- **Embeddings**: OpenAI `text-embedding-3-large` (3072d)
- **LLM**: OpenAI / DeepSeek / Groq (chat-only)
- **Sparse**: Qdrant native BM25 via `fastembed`
- **Backend**: Python 3.12, FastAPI, sse-starlette, langchain / langgraph
- **Frontend**: React 18 + Vite + TypeScript, KaTeX

## Mount from zero

This repo ships **code only**. No data, no Qdrant collections, no `.env`.
A receiver builds the full system locally:

```bash
# 1. clone + Python venv
git clone https://github.com/IohanFaustino/statrag.git && cd statrag
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 2. provide secrets
cp .env.example .env
# edit .env: fill OPENAI_API_KEY (required);
#            DEEPSEEK_API_KEY / GROQ_API_KEY optional

# 3. start Qdrant (empty)
docker compose -f ops/docker/docker-compose.yml up -d

# 4. install frontend
cd web && npm install && cd ..

# 5. ingest at least one book to populate Qdrant
#    book yaml configs live under src/ingestion/books/
#    raw OCR sources must be provided by the user (NOT shipped here)
python -m src.ingestion.pipeline --book <slug> --chapter chNN

# 6. run dev stack (backend :8766 + frontend :5175)
./scripts/dev.sh
```

Open <http://localhost:5175>.

## Ingesting your own books

The system starts with **empty Qdrant collections**. To make the tutor mode
useful you must ingest at least one OCR-cleaned Markdown textbook. The full
operational guide lives in **[`docs/tasks/ingestion.md`](docs/tasks/ingestion.md)**
— read that first. Summary of the user-facing path:

1. **Locate chapter boundaries** in your `.md` source:
   ```bash
   grep -n "^# \|^## [0-9]\|^### [0-9]\+\.1\s" /path/to/book.md | head -40
   ```
2. **Write `src/ingestion/books/<slug>.yaml`** with `slug`, `name`, `field`
   (collection prefix, e.g. `econometrics`), `theme`, `authors`, `edition`,
   `year`, `source_path`, and a `chapters:` map of `line_start` / `line_end`.
   Template + every required field is in
   [`docs/tasks/ingestion.md`](docs/tasks/ingestion.md#required-yaml-fields).
3. **(Optional) Extract index + bibliography** into
   `data/parsed/<slug>/book.json` for better retrieval payload filters.
4. **Preview ingest** one section (~1 LLM call, no manifest write):
   ```bash
   .venv/bin/python -m src.ingestion.pipeline \
     --book <slug> --chapter ch01 --limit-sections 1 --force
   ```
5. **Full ingest** all chapters once preview looks right:
   ```bash
   .venv/bin/python -m src.ingestion.pipeline --book <slug>
   ```
6. **Verify** invariants on the resulting Qdrant state — see
   [`docs/tasks/ingestion.md`](docs/tasks/ingestion.md) "Verify" section.

### Easy path: Claude Code

If you use Claude Code, the repo also defines a `rag-add-book` skill that
runs steps 1–5 end-to-end with three confirmation gates (yaml → preview →
full ingest). Drop the skill into your local `.claude/skills/` and invoke
it; the skill itself follows the recipe in `docs/tasks/ingestion.md`, so
that doc is the single source of truth either way.

## Ports

| Profile | Frontend | Backend | Qdrant |
|---|---|---|---|
| dev (`./scripts/dev.sh`) | 5175 | 8766 | 6333 |
| prod (`docker compose --profile prod up`) | 5173 | 8765 | 6333 |

Qdrant dashboard: <http://localhost:6333/dashboard>.

## Security notes for self-hosting

- `.env` is git-ignored. Never commit it. `.env.example` lists required keys.
- CORS is `allow_origins=["*"]` in `src/services/chat/api.py` for dev
  convenience. **Restrict before exposing publicly.**
- `/api/figures` whitelists local filesystem roots in `src/services/chat/api.py`.
  Edit the `_FIGURE_ROOTS` list to match your machine — hardcoded paths are
  author-specific.

## Docs

- [`CLAUDE.md`](CLAUDE.md) — architecture + Chinese wall + commands
- [`docs/system/architecture.md`](docs/system/architecture.md)
- [`docs/system/invariants.md`](docs/system/invariants.md)
- [`docs/services/chat.md`](docs/services/chat.md)
- [`docs/tasks/ingestion.md`](docs/tasks/ingestion.md)

## License

Personal research project. No license granted by default — contact author.
