# P8 — Agentic RAG (Polzer)

Build agentic RAG workflows w/ tools. Loop: query → tool select → retrieve → assess → continue/answer.

**Relevance**: very high.
- Direct template for Service 1 follow-ups (tutor decides whether to re-retrieve).
- "Assess + continue" loop = self-correcting retrieval.

**Take**: agentic mode = LLM gets retrieval as tool, can call N times. Bound N to 3 to cap cost. Use for tutor + research-assistant.
