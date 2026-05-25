"""Chat service — SSE-streaming conversational layer over hybrid retrieval.

Chinese-wall rule:
- Imports only from `src.core`.
- Never imports from other services or from `src.ingestion`.
- Reads `data/parsed/manifest.json` and `src/ingestion/books/*.yaml` as
  filesystem artifacts only (no module import into ingestion).
"""
