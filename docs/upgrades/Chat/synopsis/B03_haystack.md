# B3 — Intro to Haystack

Components, pipelines (graphs), SuperComponents, agents + tools, **dense vs sparse retrieval (BM25 + embedding)**, hybrid retrieval, RAG-as-a-tool, multi-tool agent. Document stores, component categories.

**Relevance to chat RAG**: high (concept) / not framework adoption.
- Hybrid retrieval pattern matches our setup.
- Component-graph mental model → use for our `Pipeline` class shape.
- Strict data contracts between stages → enforce in services/.

**Take**: keep architecture inspired by Haystack but don't import the framework. We're FastAPI-native.
