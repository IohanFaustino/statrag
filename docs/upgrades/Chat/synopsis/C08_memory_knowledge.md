# C8 — Agent Memory + Knowledge (Lanham)

RAG as memory + knowledge. File-ingest path, retrieval as recall mechanism, conversation memory via vector store.

**Relevance**: very high for Service 1 (tutor).
- Same vector store for both corpus knowledge + conversation history → matches abstract.md Option 3 (long-term tutor memory).
- Clarifies: knowledge = static + ingested; memory = dynamic + per-conversation.

**Take**: dual-collection memory: `corpus_*` (read-only) + `conv_<id>` (per-conversation, ephemeral). Separate namespaces.
