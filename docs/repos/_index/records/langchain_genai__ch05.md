# code:langchain_genai:ch05 — Building Intelligent Agents

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch05
chapter_title: Building Intelligent Agents
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter5

## Summary
Chapter 5 builds LLM agents from scratch, covering tool-calling mechanics, the ReAct pattern, and structured output. Notebooks progress from raw OpenAI function-calling JSON to LangChain's `@tool` decorator, LangGraph `ToolNode` with automatic tool dispatch, a hand-rolled ReAct loop with mocked tools, structured output via Pydantic + `with_structured_output`, and a full Plan-and-Solve agent that decomposes tasks into a typed Plan before executing each step. The chapter demonstrates both `create_react_agent` and bespoke LangGraph state machines for agent control flow.

## Libraries & frameworks
IPython, config, datetime, langchain_community, langchain_core, langchain_experimental, langchain_google_genai, langchain_openai, langgraph, math, numexpr, operator, os, pydantic, sys, typing

## Models & APIs
`gemini-2.5-flash` (ChatGoogleGenerativeAI — primary model across most notebooks), `gpt-4` (ChatOpenAI in react_example as alternative), DuckDuckGoSearchRun (built-in search tool)

## Concepts / patterns
Tool-calling / function-calling (raw JSON and LangChain `@tool` decorator), `BaseTool`, `ToolNode` with `tools_condition` in LangGraph, `create_react_agent` prebuilt executor, hand-built ReAct loop (reason-act-observe), structured output with Pydantic (`with_structured_output`), Plan-and-Solve agent pattern (two-stage: plan generation then step execution), numexpr calculator tool.

## Files
- README.md — Chapter overview with per-notebook Colab/Kaggle links (md)
- built-in_tools.ipynb — Uses DuckDuckGoSearchRun with Gemini-2.5-flash via raw tool invocation and create_react_agent (py)
- custom_tools.ipynb — Defines a numexpr-based calculator with @tool decorator, wraps it in create_react_agent (py)
- plan_and_solve.ipynb — Implements a Plan-and-Solve agent: Pydantic Plan structured output then step-by-step LangGraph execution (py)
- react_example.ipynb — Hand-rolls a ReAct agent loop with mocked Google search and calculator tools, using gpt-4 (py)
- structured_output.ipynb — Demonstrates Pydantic structured output (with_structured_output) and JSON mode for step-by-step planning (py)
- tool_node.ipynb — Builds a LangGraph graph with ToolNode and tools_condition for automatic search/calculator dispatch (py)
- tools_langchain.ipynb — Overview of LangChain tool abstractions and BaseTool interface (py)
- tools_with_llm_example.ipynb — Shows raw OpenAI-style function-calling JSON integrated with LangChain (py)

## Code entities
- custom_tools.ipynb: calculator, calculator, CalculatorArgs, calculator, calculator, calculator
- plan_and_solve.ipynb: Plan, CalculatorArgs, calculator, StepState, PlanState, get_current_step, get_full_plan, _build_initial_plan, _run_step, _get_final_response, _should_continue
- react_example.ipynb: mocked_google_search, mocked_calculator, invoke_llm, call_tools, should_run_tools, mocked_google_search_tool, mocked_calculator_tool
- structured_output.ipynb: Step, Plan
- tool_node.ipynb: calculator, invoke_llm, get_date, time_difference

## Key snippets
```python
# @tool decorator with numexpr calculator (custom_tools.ipynb)
from langchain_core.tools import tool
import numexpr as ne, math

@tool
def calculator(expression: str) -> str:
    """Calculates a single mathematical expression, incl. complex numbers."""
    math_constants = {"pi": math.pi, "i": 1j, "e": math.exp}
    return str(ne.evaluate(expression.strip(), local_dict=math_constants))

from langgraph.prebuilt import create_react_agent
agent = create_react_agent(llm, [calculator])
```

```python
# LangGraph ToolNode with tools_condition (tool_node.ipynb)
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import MessagesState, StateGraph, START, END

builder = StateGraph(MessagesState)
builder.add_node("invoke_llm", invoke_llm)
builder.add_node("tools", ToolNode([search, calculator]))
builder.add_edge(START, "invoke_llm")
builder.add_conditional_edges("invoke_llm", tools_condition)
```

```python
# Structured output via Pydantic (structured_output.ipynb)
class Plan(BaseModel):
    steps: list[Step]

result = (prompt | llm.with_structured_output(Plan)).invoke({"task": "..."})
```
