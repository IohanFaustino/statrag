# Hindsight Implementation Options — per-turn mode orchestrator / dispatcher
_generated 2026-06-02 · bank claude-code · facets: pattern, infra, models, pitfalls_

## Weighted sources
- Generative AI with LangChain ch.3, ch.5, ch.6 · Agentic Patterns ch.14, ch.15

## How others built it (pattern)
- **Typed-state dispatch (`LoanGraphState` TypedDict + 7 deterministic nodes + conditional edges via `check_error`)** — a single state object carries the routing field; conditional edges select the next node from it. The exact analog of routing a turn by a `mode` field. · src: Agentic Patterns ch.15 · repo `agentic_patterns` · `Chapter_15_Agents.ipynb`
- **Orchestrator-workers (FCoT `LoanOrchestrator` delegates to 4 specialist sub-agents wrapped as `AgentTool`s)** — a thin dispatcher routes to specialist pipelines; our 4 modes are the specialists. · src: Agentic Patterns ch.14 · repo `agentic_patterns`
- **LangGraph `StateGraph` conditional edges (`is_suitable_condition` on `JobApplicationState`)** — node chosen from a state predicate; error handling on the edge. · src: Generative AI with LangChain ch.3 · repo `langchain_genai` · `langgraph_intro.ipynb`
- **`ToolNode` + `tools_condition` dispatch** — declarative routing table from a condition to a handler. · src: Generative AI with LangChain ch.5 · repo `langchain_genai` · `tool_node.ipynb`

## Stack options (infra)
- **LangGraph `StateGraph` + `MemorySaver`/`InMemoryStore`** — graph state + per-thread persistence; cross-session memory stored under a namespace (`('users','user1')`). Analog: persist per-message/per-turn mode + state. · src: Generative AI with LangChain ch.3/ch.6 · repo `langchain_genai`
- **TypedDict state schema** — explicit, testable routing state (vs implicit globals). · src: Agentic Patterns ch.15

## Model choices (models)
- **Multi-provider switching (OpenAI / Anthropic / Google / Ollama / HuggingFace)** — incl. local `deepseek-r1:1.5b` (Ollama) and `TinyLlama`; supports "test with any model (kimi/ollama)". · src: Generative AI with LangChain ch.2 · repo `langchain_genai`
- **`gemini-2.5-flash`** — used as the orchestrator/multi-agent model across ch.6 + Agentic ch.13/14. · src: Agentic Patterns ch.14

## Pitfalls & evals (pitfalls)
- **Explicit error edges, no silent fallback (`check_error` conditional edge)** — route failures to a visible error path, not a default node. Matches our `MODE_NOT_ROUTED`/`MODE_NOT_REGISTERED` loud-fail. · src: Agentic Patterns ch.15
- **Robustness wrapper (`tenacity` backoff ≤5 + `ratelimit`)** around each delegated call. · src: Agentic Patterns ch.14
- **Agent-trajectory evaluation (`trajectory_subsequence`, `run_graph_with_trajectory`)** — verify the right sequence of nodes/agents ran. Analog: our per-mode routing-contract test. · src: Generative AI with LangChain ch.8 · `advanced_evaluation.ipynb`

## Synthesized approaches   <!-- handoff to brainstorming -->
1. **Per-message mode persisted, routed by the existing dispatch table (recommended)** — store each turn's mode in message metadata; the `_V2_DISPATCH` table (already built) routes by `req.mode`; the picker sets the NEXT turn's mode and is no longer reset on open. Draws on ch.15 (typed-state dispatch field) + ch.14 (orchestrator→specialists) + ch.6 (namespaced per-turn persisted state). Tradeoff: small schema/metadata change; deterministic, no new latency.
2. **Full LangGraph mode-router node** — a router node keyed on a `mode` state field with conditional edges to each pipeline (ch.3/ch.15 style). Tradeoff: large refactor toward LangGraph for the whole chat; the dispatch table already gives this routing without it.
3. **Auto-classify router (LLM picks the mode)** — reflection/structured-output classifier (ch.6) chooses the mode; picker becomes override. Tradeoff: adds latency + a classification failure mode; deferred (user chose per-turn manual).
