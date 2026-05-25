# B7 — Deploying Haystack Apps

FastAPI vs Hayhooks, Dockerize pipeline, endpoint security/validation, CI/CD, serialization, **MCP server exposure**, secure endpoints, Qdrant prod notes.

**Relevance to chat RAG**: medium-high.
- FastAPI patterns + Docker → we use FastAPI already (`src/services/chat/api.py`); validate against book.
- MCP server idea → future expose retrieval as MCP tool.
- Endpoint validation patterns → input schema + rate limiting for chat API.

**Take**: harden chat API: request validation, auth, rate limit, structured errors. Defer MCP.
