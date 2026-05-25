# B5 — Haystack Custom Components

Component contract (run sig + outputs), warm_up() for heavy resources, **Ragas eval framework**, **KnowledgeGraphGenerator + SyntheticTestGenerator** from PDFs/websites, multi-source unification, testing/debugging components.

**Relevance to chat RAG**: high.
- Synthetic test generator → directly build our retrieval/answer eval set from `data/parsed/`.
- Ragas → metrics for `Chat/test_plan.md` (faithfulness, context precision/recall, answer relevance).
- Component testing principles → unit test shape for our retriever/assembler/generator.

**Take**: synthesize eval set from textbook sections; use Ragas metrics; testable component boundary.
