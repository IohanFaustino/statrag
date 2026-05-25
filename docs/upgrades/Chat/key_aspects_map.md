# Key Aspects Map — RAG Chat System

Match each system need to chapters that cover it.
`A` = Building AI Agents · `B` = Funderburk Pipelines · `C` = Lanham Agents in Action · `P` = Polzer RAG Cookbook.

## 1. Retrieval pipeline (core)

| Need | Primary | Secondary |
|------|---------|-----------|
| Dense embeddings + similarity | A1, A5, P5 | B2 |
| Sparse (BM25) + hybrid | B3, B4 | A6 |
| Chunking strategy | A5, P4 | B4 |
| Metadata enrichment / filter | P4, P7 | — |
| Hierarchical indexing | A6 | — |
| Reranker (cross-encoder) | A6, P7 | B4 |
| Query routing (mode dispatch) | A6, P7 | B8 |
| Query rewriting / HyDE | P7, A6 | B2 |
| Multi-query retrieval | P7 | B4 |
| Query decomposition | P7 | A9 |
| Context enrichment (adjacent chunks) | A6 | — |
| Multimodal (figures, captions) | B4 (Strategy 2), P3 | A6 |
| Vector DB perf tuning | P6 | — |

## 2. Prompting + Generation

| Need | Primary | Secondary |
|------|---------|-----------|
| Prompt engineering / ICL | A3, C2 | B2 |
| Prompt templates per task | P2 | C2 |
| Context engineering (2025) | B2 | B8 |
| Hallucination mitigation + citation | A3, A5 | — |
| Chain-of-thought | C10 | — |
| Self-check / self-eval | C10 | — |
| Token budgeting | A2, B2 | B6 (cost) |
| Model selection per mode | A3, C2, P2 | B2, B6 |
| Local models (Ollama / LM Studio) | C2, P2 | — |
| Persona / profile per mode | C7 | — |

## 3. Agent architecture

| Need | Primary | Secondary |
|------|---------|-----------|
| Single-agent baseline | A4, C1 | B3 |
| Multi-agent (orchestrator + workers) | A9, B8, C4 | — |
| Role-based crew (CrewAI shape) | C4 | A9 |
| Group chat (AutoGen shape) | C4 | — |
| Supervisor / approval gate | B8 | — |
| Clarification node | B8 | C11 |
| Tool layer vs orchestration layer | B1, B2 | B10 |
| Function calling / tool invocation | C5 | P8 |
| Agentic RAG loop (LLM calls retrieval) | P8 | C5 |
| HuggingGPT 4-step pattern | A9 | — |
| Brain/perception/action paradigm | A4 | C1 |
| Behavior trees / ABT | C6 | — |
| Planning + feedback loops | C11 | — |

## 4. Memory + state

| Need | Primary | Secondary |
|------|---------|-----------|
| Conversation memory (sliding, summary, vec) | B2, C8 | A3 |
| Knowledge vs memory split | C8 | — |
| Agentic memory consolidation | B2 | — |
| State schema (intent, results, QC) | B8 | — |
| Persisted plan + checkpoints | C11 | — |

## 5. Knowledge graphs

| Need | Primary | Secondary |
|------|---------|-----------|
| KG concept + entity/relation extraction | A7, P9 | B5 |
| GraphRAG | A7, P9 | — |
| Practical KG-build recipes (Python) | P9 | A7 |
| Cycle detection (DAG of prereqs) | A7 | — |

## 6. Evaluation + Testing

| Need | Primary | Secondary |
|------|---------|-----------|
| Faithfulness / context precision / recall | A5, P10 | B5 (Ragas), B6 |
| Automated metrics | P10 | B5 |
| Human-judgment rubric | P10 | — |
| Synthetic eval set from corpus | P10, B5 | — |
| LLM-as-judge | B6, P10 | — |
| Prompt regression test | C9 | — |
| Component unit tests | B5 | — |
| Observability (logs, metrics, costs) | B6 | A10 |

## 7. Deployment + Ops

| Need | Primary | Secondary |
|------|---------|-----------|
| FastAPI app | B7 | — |
| Docker | B7, P11 | A10 |
| AWS deploy (optional) | P11 | — |
| Endpoint security + validation | B7 | — |
| CI/CD | B7 | B6 |
| MCP server expose (future) | B7, B9 | — |
| Async / parallel pipelines | B4 | A10 |

## 8. Cross-mapping to abstract.md services

| Service | Architecture insight | Source |
|---------|---------------------|--------|
| 1. Tutor | Single + memory (sliding/summary/vec) + agentic loop | B2, A3, C8, P8 |
| 2. Cross-book | Dual retrieval + parallel + multi-query | B4, A6, P7 |
| 3. Figure-aware | Vision-RAG Strategy 2 + caption gate | B4, P3 |
| 4. Quiz | 2-stage chain + self-check + CoT | A3, B5, C10 |
| 5. Navigator | Query expansion + HyDE + structured location output | A6, P7 |
| 6. Prereq tracer | Multi-agent + KG (Polzer recipes) + cycle detection | A7, P9, A9, B8 |
| 7. Annotated reading | Batch parallel retrieval + threshold + multi-query | A6, B4, P7 |
| 8. Research assistant | Multi-agent (claim + retriever + stance) + decomposition | A9, B8, C4, P7 |
| 9. Math explainer | Multimodal + vision gate + LaTeX + CoT | B4, A6, C10 |
| 10. Study path | Multi-agent + state + replanning + plan/feedback | B8, A9, C11 |
| 11. Roadmap | Multi-query + structured YAML output + decomposition | A6, B5, P7 |
