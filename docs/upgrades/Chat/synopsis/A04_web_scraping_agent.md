# A4 — Building a Web Scraping Agent

Brain/perception/action paradigm, agent properties (autonomy, reactivity, proactiveness, social), single vs multi-agent, libraries (LangChain, Haystack, LlamaIndex, Semantic Kernel, AutoGen), framework choice, sample web agent.

**Relevance to chat RAG**: medium-high.
- Library comparison → informs framework pick. We are framework-light (FastAPI + custom). Use LangChain/LangGraph patterns selectively.
- Brain/perception/action → maps onto our Query Processor / Retriever / Generator pipeline.
- Single-agent property check → use as gate before promoting to multi-agent (mirrors abstract.md principle).

**Take**: adopt single→multi promotion criteria; not adopting full framework.
