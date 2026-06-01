# Hindsight Implementation Options — facilitate concept-map teaching mode
_generated 2026-06-01 · bank claude-code · facets: pattern, infra, models, pitfalls_

## Weighted sources
- Generative AI with LangChain ch.4, ch.5, ch.6, ch.8 · RAG-Driven Generative AI ch.5, ch.7 · Agentic Architectural Patterns ch.14

## How others built it (pattern)
- **Plan-and-Solve / structured Plan state machine** — a planner LLM emits a typed `Plan` (Pydantic `with_structured_output`), then a solver walks each step. Maps directly to "extract a concept-map first, then teach each node." · src: Generative AI with LangChain ch.5 · repo langchain_genai · plan_and_solve.ipynb, structured_output.ipynb
- **Orchestrator–workers with sub-agents-as-tools + Recap→Reason→Verify (FCoT)** — an orchestrator delegates to specialist sub-agents wrapped as tools, looping Recap→Reason→Verify. Model for "map builder → per-concept retrieval worker → simplifier → verify." · src: Agentic Architectural Patterns ch.14 · repo agentic_patterns
- **Four-node RAG graph: retrieve → generate → double-check → finalise** — a compact LangGraph with an explicit grounding/double-check node before finalising; `format_sources_with_citations` + `verify_response_accuracy`. The concept-explanation sub-retrieval + footnote grounding mirrors this. · src: Generative AI with LangChain ch.4 · repo langchain_genai · rag.py, 04_advanced_rag_techniques.ipynb
- **Tree-of-Thoughts planner + voting** — planner proposes multiple structured plans, votes the best. Optional: vote among candidate concept-maps for the cleanest teaching order. · src: Generative AI with LangChain ch.6 · repo langchain_genai

## Stack options (infra)
- **Per-item on-demand retrieval (query expansion + contextual compression + MMR)** — advanced retrieval techniques to fetch a *focused* explanation for one concept, then compress to the relevant span. Directly supports per-concept sub-retrieval. · src: Generative AI with LangChain ch.4 · repo langchain_genai · 03_retrieval_techniques.ipynb, 04_advanced_rag_techniques.ipynb
- **Hybrid Adaptive RAG (strategy chosen per item)** — pick retrieval strategy per query (none / inject / full RAG) by a score; analog: same-author-nearest-section first, fall back to other authors only if score low. · src: RAG-Driven Generative AI ch.5 · repo rothman_rag · Adaptive_RAG.ipynb
- **Re-ranking of query results** — re-rank retrieved candidates before use (our hybrid_search already supports rerank). · src: RAG-Driven Generative AI ch.7 · repo rothman_rag
- **self-consistency citation checking / `verify_response_accuracy`** — verify each generated claim against sources; basis for grounding concept explanations as footnotes. · src: Generative AI with LangChain ch.4 · repo langchain_genai

## Model choices (models)
- **Structured extraction/planning via `with_structured_output` (Pydantic)** — typed concept-map output; the reliable way to get ordered nodes + flags. · src: Generative AI with LangChain ch.5 · repo langchain_genai
- **Planner at temperature 1.0 + voting (gemini-2.5-flash in book)** — only if we add ToT voting over maps; otherwise temp 0 for determinism. · src: Generative AI with LangChain ch.6
- **Cheap retrieval/generation model + separate eval model** — book splits roles: llama-3.3-70b (retrieval), text-embedding-3-large (embeddings), ChatOpenAI (query-expansion + eval). Maps to our nano/qwen + text-embedding-3-large stack; use a stronger model only for the simplify/teach node. · src: Generative AI with LangChain ch.4

## Pitfalls & evals (pitfalls)
- **Long system prompts cause prompt-adherence failure** — (our own DEEP_TUTOR_INSTRUCTIONS ~3500 tok degraded the draft model). Keep each node's prompt short + single-purpose; do NOT merge map+teach+simplify into one mega-prompt. · src: project changelog (deep-tutor) — corroborated by ch.4 modular node design
- **Faithfulness > fluency: double-check node + self-consistency citation checking** — a dedicated verify pass (`verify_response_accuracy`) catches hallucinated concept explanations before they ship as footnotes. · src: Generative AI with LangChain ch.4
- **Multi-dimensional LLM-as-judge eval (accuracy / completeness / clarity / conciseness)** — the right eval rubric for "facilitate" since the goal is clarity + key-point filtering, not length. Use as the offline scorer when testing prompt/structure variants. · src: Generative AI with LangChain ch.8 · basic_evaluators.ipynb, advanced_evaluation.ipynb

## Synthesized approaches   <!-- handoff to brainstorming -->
1. **Concept-map-first, two-pass (Plan-and-Solve + adaptive sub-retrieval)** — Pass A: a map-builder LLM emits a typed `ConceptMap` per section (key concepts, theorems, formulas, ordered flow, + each concept flagged "explained-in-section" vs "referenced-only"). Pass B: for each referenced-only concept, an adaptive sub-retrieval (same-author → nearest prior section → formal-statement preference → fallback other authors), then a short simplify-and-teach node renders the section as **filtered key points in plain language** with the concept as a clickable anchor backed by the retrieved explanation (footnote on export). A final verify node grounds explanations. Draws on [ch.5 Plan-and-Solve, ch.4 four-node RAG+verify, ch.5-rothman adaptive]; tradeoff: 2 LLM passes + N sub-retrievals/section = more latency/cost, but cleanly separates "what to teach" from "how to explain," each with a short prompt.
2. **Single orchestrator-workers pass (FCoT)** — one orchestrator per section delegates to map / retrieve / simplify sub-agents as tools in a Recap→Reason→Verify loop. Draws on [ch.14]; tradeoff: fewer round-trips and adaptive tool use, but harder to make output deterministic/streamable and to enforce the typed concept-map schema; tool-calling adds failure modes.
3. **Map + ToT-voted teaching order** — build several candidate concept-maps and vote the clearest teaching order before the per-concept pass. Draws on [ch.6]; tradeoff: better pedagogical ordering for messy sections, but extra cost and our sections are already author-ordered (order-preservation is a hard invariant), so voting on order largely conflicts with the existing structural-order rule — likely YAGNI.
