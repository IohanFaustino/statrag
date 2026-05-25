# A6 — Advanced RAG Techniques

Naive-RAG issues, advanced pipeline: **hierarchical indexing, HyDE / hypothetical questions, context enrichment, query transformation, hybrid search, query routing, reranking, response optimization, modular RAG, training vs training-free**. Scalability, parallelism, security/privacy, open problems.

**Relevance to chat RAG**: highest single chapter.
- HyDE + query transformation → directly addresses cross-book vocabulary mismatch (abstract problem #2).
- Hybrid search + reranking → we already have dense+sparse, missing reranker.
- Query routing → mode dispatch (tutor vs navigator vs quiz).
- Hierarchical indexing → could help: book → chapter → section drill-down.
- Context enrichment → adjacent-chunk fetch to fix "figure shown without explanatory section" issue.

**Take**: this chapter drives Phase 2 retrieval upgrades. Reranker is highest-ROI addition.
