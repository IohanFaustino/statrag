# P7 — Advanced Retrieval (Polzer)

**Metadata filtering, multi-query retrieval, HyDE, reranking, query decomposition.**

**Relevance**: HIGHEST. Direct recipes for our Phase 2 retrieval upgrades.
- Multi-query → Service 2 (cross-book), Service 11 (roadmap).
- HyDE → cross-book vocabulary mismatch (abstract problem #2 + #5).
- Reranking → missing layer in current pipeline.
- Query decomposition → Service 8 (claim extractor), Service 10 (goal decomposer).
- Metadata filter → mode-specific (book/chapter/theme).

**Take**: this chapter = blueprint for `retrieval/v2`. Each technique becomes a composable stage.
