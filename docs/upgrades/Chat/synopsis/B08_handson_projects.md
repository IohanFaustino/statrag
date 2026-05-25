# B8 — Hands-On Projects + Agentic Orchestration

Haystack agent recap, built-in agent limits (thought→action→observation), **LangGraph alternative**, NER, text classification, sentiment, **multi-agent orchestration with supervisor + clarification + approval nodes**, agent state schema, workers + supervisor + graph build.

**Relevance to chat RAG**: very high for multi-agent services.
- LangGraph state schema (user intent, node results, final output, QC) — adopt for services 6/8/10.
- Supervisor approval node → groundedness/QC gate before returning to user.
- Clarification node → useful for Service 5 (navigator) + Service 10 (study path goal calibration).

**Take**: implement multi-agent services on a minimal LangGraph-shaped state machine. Supervisor = QC + cite check.
