# A5 — Extending Agent with RAG to Prevent Hallucinations

Naive RAG, chunking strategies, embedding strategies, vector DBs (perf params: search latency vs recall), evaluation of output, **RAG vs fine-tuning**, movie recommender build.

**Relevance to chat RAG**: very high.
- Chunking strategies — validate our "1 section = 1 chunk, split at 8000 tok" decision.
- Embedding strategies — confirm `text-embedding-3-large` and whether to add domain re-embedding.
- Eval output — direct input for `Chat/test_plan.md` (faithfulness, answer relevance, context precision/recall).
- RAG-vs-FT — argues we stay RAG-only (no fine-tune needed).

**Take**: pull eval metric list directly into test plan.
