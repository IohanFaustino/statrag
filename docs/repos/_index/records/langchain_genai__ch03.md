# code:langchain_genai:ch03 — Building Workflows with LangGraph

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch03
chapter_title: Building Workflows with LangGraph
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter3

## Summary
Chapter 3 teaches LangGraph state machine construction through a running job-application example and several advanced workflow patterns. Notebooks cover StateGraph with conditional edges, enum and Pydantic output parsers, try/except error-handling nodes, in-memory and LangGraph checkpoint-backed conversation memory, multimodal inputs (images and video via Gemini), a map-reduce pattern for long-video summarisation, and self-consistency voting for math reasoning. Together they show how to build robust, production-grade LLM workflows that survive parse failures and manage memory across turns.

## Libraries & frameworks
IPython, base64, collections, enum, langchain, langchain_core, langchain_google_genai, langgraph, logging, operator, pydantic, typing, typing_extensions

## Models & APIs
`gemini-2.5-flash` (ChatGoogleGenerativeAI — used throughout as the primary reasoning model), `gemini-2.0-flash` (alternative in some notebooks)

## Concepts / patterns
LangGraph StateGraph, typed state (TypedDict), conditional edges, EnumOutputParser, Pydantic structured output, error-handling nodes with try/except, RunnableWithMessageHistory in-memory conversation memory, MemorySaver checkpointer, map-reduce over video chunks, self-consistency voting (chain-of-thought sampling + Counter majority), multimodal (image bytes and GCS video URIs with Gemini).

## Files
- README.md — Chapter overview with per-notebook Colab/Kaggle links (md)
- error_handling.ipynb — Wraps LangGraph nodes in try/except; uses MessagesIterator fake LLM to simulate intermittent failures (py)
- langgraph_intro.ipynb — Builds the core JobApplicationState graph with conditional edge is_suitable_condition and custom reducers (py)
- map_reduce.ipynb — Implements a parallel map-reduce pipeline that splits a GCS video into chunks, summarises each with Gemini, then merges (py)
- memory.ipynb — Adds per-session conversation memory using RunnableWithMessageHistory + InMemoryChatMessageHistory and MemorySaver (py)
- multimodality.ipynb — Passes base64 images and GCS video URIs to Gemini-2.5-flash via LangChain HumanMessage content parts (py)
- output_parsers.ipynb — Demonstrates EnumOutputParser and Pydantic structured output inside a LangGraph job-suitability workflow (py)
- prompt_templates.ipynb — Shows PromptTemplate and ChatPromptTemplate usage in the workflow context (py)
- retry_with_error_output_parser.ipynb — Uses RetryWithErrorOutputParser to re-prompt on malformed model output (py)
- self_consistency.ipynb — Runs a CoT math chain 20× with temperature 2.0 and picks the majority answer via collections.Counter (py)

## Code entities
- error_handling.ipynb: IsSuitableJobEnum, analyze_job_description, MessagesIterator, JobApplicationState, generate_application, is_suitable_condition, analyze_job_description, analyze_job_description
- langgraph_intro.ipynb: JobApplicationState, analyze_job_description, generate_application, is_suitable_condition, JobApplicationState, analyze_job_description, generate_application, JobApplicationState, analyze_job_description, generate_application, my_reducer, JobApplicationState, analyze_job_description, generate_application, generate_application
- map_reduce.ipynb: _create_input_messages, _merge_summaries, AgentState, _ChunkState, _summarize_video_chunk, _map_summaries, _generate_final_summary
- memory.ipynb: PrintOutputCallback, get_session_history, test_node
- output_parsers.ipynb: IsSuitableJobEnum, JobApplicationState, analyze_job_description, is_suitable_condition, generate_application
- retry_with_error_output_parser.ipynb: SearchAction

## Key snippets
```python
# LangGraph StateGraph with conditional edge
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict
from typing import Literal

class JobApplicationState(TypedDict):
    job_description: str
    is_suitable: bool
    application: str

builder = StateGraph(JobApplicationState)
builder.add_node("analyze_job_description", analyze_job_description)
builder.add_node("generate_application", generate_application)
builder.add_conditional_edges("analyze_job_description", is_suitable_condition)
graph = builder.compile()
```

```python
# Self-consistency voting
from collections import Counter

generations = [final_chain.invoke({"question": q}, temperature=2.0).strip() for _ in range(20)]
best = Counter(generations).most_common(1)[0][0]
```
