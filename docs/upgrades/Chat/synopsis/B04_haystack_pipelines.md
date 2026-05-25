# B4 — Haystack Pipelines for Use Cases

Pipeline design (branching, data flow, visualization, third-party integrations), indexing pipeline (FileTypeRouter → preprocess → unified index), naive RAG, **hybrid RAG with reranking** (parallel retrieve → fusion → rerank → augment+gen), SuperComponent reuse, **multimodal (CLIP joint embeddings vs LLM-extraction + vision RAG)**, audio, parallel + async pipelines.

**Relevance to chat RAG**: highest in Book B.
- Hybrid+rerank 4-stage exactly matches what abstract needs.
- Multimodal Strategy 2 (LLM-extraction + vision RAG) directly fits Service 9 (math explainer) and 3 (figure-aware) — solves the "vision call gate" question.
- Async/parallel patterns → required for Service 2 (cross-book dual retrieval) and Service 8 (claim-extractor).

**Take**: implement reranker stage + adopt vision-RAG strategy 2 (caption-first, image-bytes on gate).
