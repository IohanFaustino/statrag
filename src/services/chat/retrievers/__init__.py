"""v2 LangChain retrievers wrapping the existing Qdrant hybrid search.

Each retriever here is a thin `BaseRetriever` subclass that delegates to
`src.services.chat.retrieval.hybrid_search` (and friends) so the existing
RRF + BM25 + dense pipeline stays the source of truth — only the API
surface changes to match LangChain conventions.

Chinese-wall: imports only from `src.core.*` and sibling `src.services.chat.*`.
"""
