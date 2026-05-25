# P5 — Embeddings (Polzer)

Embedding semantics, **model selection** (size + cost + quality), domain-fit.

**Relevance**: medium.
- Validates `text-embedding-3-large` (3072d).
- Possible alternative: `text-embedding-3-small` for query-time speed if query rewriter generates many queries (Service 8 claim splitter).

**Take**: keep large model for ingest. Consider small model for HyDE/query-rewrite (cheaper, large for storage queries only).
