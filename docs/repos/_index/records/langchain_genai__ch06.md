# code:langchain_genai:ch06 — Advanced Applications and Multi-Agent Systems

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch06
chapter_title: Advanced Applications and Multi-Agent Systems
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter6

## Summary
Chapter 6 demonstrates advanced multi-agent architectures evaluated on the MMLU high-school-geography benchmark. The main notebooks build a two-agent researcher-reflection system (research agent + professor critic), a full LangGraph reflection loop for question-answering, LangGraph streaming for real-time token output, a Tree-of-Thoughts (ToT) branching planner with voting, and LangChain/LangGraph caching strategies. Each pattern tackles a different aspect of orchestrating multiple cooperating agents with tool access (DuckDuckGo, Arxiv, Wikipedia).

## Libraries & frameworks
IPython, collections, datasets, langchain, langchain_community, langchain_core, langchain_google_genai, langgraph, operator, pydantic, typing

## Models & APIs
`gemini-2.5-flash` (ChatGoogleGenerativeAI — used in all notebooks), DuckDuckGo search, Arxiv, Wikipedia (via `load_tools`)

## Concepts / patterns
Multi-agent communication (researcher + reflection critic loop), LangGraph streaming (`.stream()` on graph with AgentState), Tree-of-Thoughts (ToT) branching with structured Plan, vote-for-best-option step, LangGraph `InMemoryStore` for cross-session memory, LangChain `InMemoryCache` for LLM response caching, `create_react_agent` with custom state schema, MMLU dataset evaluation.

## Files
- README.md — Chapter overview with per-notebook Colab/Kaggle links (md)
- cache.ipynb — Shows LangChain InMemoryCache for LLM call deduplication and LangGraph InMemoryStore for persistent cross-turn memory (py)
- communication.ipynb — Builds a research agent (student) and reflection agent (professor critic) that exchange feedback via ReflectionAgentState (py)
- question_answering.ipynb — Full LangGraph reflection pipeline for MMLU multiple-choice Q&A: ResearchState → research → reflection → final answer (py)
- streaming.ipynb — Demonstrates LangGraph streaming output from a research agent processing MMLU questions (py)
- tot.ipynb — Implements Tree-of-Thoughts: generates multiple plans via Gemini structured output, runs each plan node, votes for best, produces final response (py)

## Code entities
- communication.ipynb: _ask_question, _give_feedback, ReflectionAgentState
- question_answering.ipynb: ResearchState, ReflectionState, Response, ReflectionAgentState, _should_end, _reflection_step, _research_start, _research
- streaming.ipynb: ResearchState
- tot.ipynb: Plan, TreeNode, PlanEvaluation, PlanState, ReplanStep, _vote_for_the_best_option, _build_initial_plan, _run_node, _plan_next, _get_final_response, _should_create_final_response, _should_continue

## Key snippets
```python
# Two-agent reflection system (communication.ipynb)
research_tools = load_tools(["ddg-search", "arxiv", "wikipedia"], llm=llm)
research_agent = create_react_agent(model=llm, tools=research_tools, prompt=system_prompt)

reflection_prompt = (
    "You are a university professor reviewing a student's multiple-choice answer. "
    "Give feedback only if the answer or reasoning is flawed."
)
```

```python
# Tree-of-Thoughts planner vote (tot.ipynb)
planner = planner_prompt | ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", temperature=1.0
).with_structured_output(Plan)

# _vote_for_the_best_option selects the winning plan branch
```

```python
# LangGraph InMemoryStore for cross-session memory (cache.ipynb)
from langgraph.store.memory import InMemoryStore
store = InMemoryStore()
store.put(namespace=("users", "user1"), key="fact1", value={"message1": "My name is John."})
```
