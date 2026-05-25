# B2 — Diving Deep into LLMs

2023 baseline (attention), prompting/fine-tuning/RAG, SLM + RLM evolution, **context engineering**, LangChain/LangGraph 1.0 + Haystack 2.0, hybrid tool/orchestration arch, vector stores (RAG → agentic memory), advanced memory consolidation, inference economics.

**Relevance to chat RAG**: very high.
- Context engineering > prompt engineering — direct input to tutor memory design.
- "Vector store as enabler of context engineering" → our Qdrant role.
- Advanced memory architectures → maps to Service 1 (tutor) memory options in abstract.
- Inference economics → cost gates per mode.

**Take**: design `Context Assembler` with explicit context-engineering rules. Use cost tier per mode.
