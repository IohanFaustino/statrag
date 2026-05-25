# B6 — Reproducible Production RAG

Project setup (uv, config), **single embedding model = single vector space**, decoupled doc stores, systematic eval (Ragas), **observability with Weights & Biases**, cost-perf tradeoff between embedding sizes.

**Relevance to chat RAG**: high.
- "One embedding model rules all" → already true for us (`text-embedding-3-large`).
- Eval-as-CI workflow → adopt for chat.
- Observability → log retrieval scores, token usage, latency per mode.

**Take**: add observability hooks + Ragas-style nightly eval. Skip W&B if local-only — use SQLite + jsonl log.
