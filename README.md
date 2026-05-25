# RAG — Statistical Textbooks

Local-first Retrieval-Augmented Generation over OCR-processed statistical textbooks.
Hybrid retrieval (dense + BM25) over per-field Qdrant collections + separate
image collections. FastAPI/SSE chat backend + React/Vite frontend.

See [`CLAUDE.md`](./CLAUDE.md) for architecture, the Chinese wall, and resume protocol.

## Stack

- Qdrant 1.12.4 (Docker)
- OpenAI `text-embedding-3-large` (3072d)
- LLM: OpenAI / DeepSeek / Groq
- Python 3.12, FastAPI, sse-starlette, langchain/langgraph
- React 18 + Vite + TypeScript (KaTeX math)

## Mount from zero

This repo ships **code only**. No data, no Qdrant collections, no `.env`. The
receiver must:

```bash
# 1. clone + Python venv
git clone <this-repo> RAG && cd RAG
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 2. provide secrets
cp .env.example .env
# edit .env: fill OPENAI_API_KEY (required); DEEPSEEK_API_KEY / GROQ_API_KEY optional

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

## Ports

| Mode | Frontend | Backend | Qdrant |
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
