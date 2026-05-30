# code:agentic_patterns:ch15 — Agent Frameworks - Use Case: A Multi-Agent System for Loan Processing with CrewAI and LangGraph

book: Agentic Architectural Patterns for Building Multi-Agent Systems
slug: agentic_patterns
chapter: ch15
chapter_title: Agent Frameworks - Use Case: A Multi-Agent System for Loan Processing with CrewAI and LangGraph
repo: https://github.com/PacktPublishing/Agentic-Architectural-Patterns-for-Building-Multi-Agent-Systems (branch main)
folder: Chapter_15

## Summary
Chapter 15 implements the identical four-stage loan origination pipeline twice — once with CrewAI and once with LangGraph — to contrast the two dominant framework philosophies using Gemini 3 Flash Preview via Google GenAI SDK. The CrewAI implementation uses a hierarchical `Process` with five role-playing `Agent` objects (Document Validation Specialist, Credit Check Agent, Risk Assessment Analyst, Compliance Officer, Loan Processing Manager) each backed by a `BaseTool` subclass and a `Task` with `context` chains, all kicked off via `Crew.kickoff`. The LangGraph implementation defines a `TypedDict` state schema (`LoanGraphState`) and seven deterministic graph nodes (`node_fetch_document`, `node_validate_document`, `node_check_credit`, `node_assess_risk`, `node_check_compliance`, `node_compile_report`, `node_compile_rejection`) connected with conditional edges via `check_error` to produce a Markdown decision report. Both implementations share the same tool logic and a common `robust_execute` wrapper combining `ratelimit` (15 calls/minute) and `tenacity` retry (5 attempts, exponential backoff 4-30 s).

## Libraries & frameworks
crewai, getpass, json, langchain_core, langchain_google_genai, langgraph, os, ratelimit, tenacity, time, typing

## Models & APIs
`gemini-3-flash-preview` via `langchain_google_genai.ChatGoogleGenerativeAI` (LangGraph path) and `crewai.LLM(model="gemini/gemini-3-flash-preview")` (CrewAI path); Google API Key via `GOOGLE_API_KEY` env var.

## Concepts / patterns
Agent framework comparison (CrewAI vs. LangGraph); CrewAI role-playing agents with personas, backstories, and goals; CrewAI `Process.hierarchical` with manager delegation (`allow_delegation=True`); CrewAI `Task` context chaining for inter-agent data flow; LangGraph state machine with `TypedDict` state schema (`LoanGraphState`); LangGraph deterministic nodes (no LLM calls inside nodes, tools called directly); conditional graph edges (`check_error`) for early-exit rejection path; `BaseTool` subclassing for CrewAI tool integration; shared tool logic across both frameworks; rate limiting + exponential backoff `robust_execute` wrapper; graceful structured error reporting (`handle_execution_error`); three test scenarios (happy path, low-credit denial, missing-field rejection).

## Files
- Chapter_15_Agents.ipynb — Implements the same four-stage loan origination pipeline using both CrewAI (hierarchical role-playing crew) and LangGraph (deterministic state-machine graph) to compare framework design philosophies on identical business logic. (py)

## Code entities
- Chapter_15_Agents.ipynb: is_rate_limit_error, robust_execute, handle_execution_error, get_document_content, ValidateDocumentFieldsTool, QueryCreditBureauAPITool, CalculateRiskScoreTool, CheckLendingComplianceTool, get_document_content, LoanGraphState, node_fetch_document, node_validate_document, node_check_credit, node_assess_risk, node_check_compliance, node_compile_report, node_compile_rejection, check_error

## Key snippets

```python
# CrewAI: hierarchical crew with manager agent and task context chaining
loan_crew = Crew(
    agents=[doc_specialist, credit_analyst, risk_assessor, compliance_officer],
    tasks=[task_validate, task_credit, task_risk, task_compliance, task_report],
    process=Process.hierarchical,
    manager_agent=manager,  # manager has allow_delegation=True
    verbose=True
)
result = robust_execute(loan_crew.kickoff, inputs={'document_content': valid_json})
```

```python
# LangGraph: TypedDict state schema + deterministic nodes + conditional edge
class LoanGraphState(typing.TypedDict):
    applicant_id: str; document_id: str; document_content: str
    validation_status: str; customer_id: str; loan_amount: int
    credit_score: int; risk_score: int; risk_level: str
    compliance_status: str; final_decision: str; error: str

workflow = StateGraph(LoanGraphState)
workflow.add_node("fetch", node_fetch_document)
workflow.add_node("validate", node_validate_document)
workflow.add_node("credit", node_check_credit)
workflow.add_node("risk", node_assess_risk)
workflow.add_node("compliance", node_check_compliance)
workflow.add_conditional_edges("validate", check_error,
    {"error": "reject", "ok": "credit"})
```

```python
# Shared robust_execute: rate-limit + tenacity wrapping any callable
@sleep_and_retry
@limits(calls=15, period=60)
@retry(stop=stop_after_attempt(5),
       wait=wait_exponential(multiplier=2, min=4, max=30),
       retry=retry_if_exception(is_rate_limit_error), reraise=True)
def robust_execute(func, *args, **kwargs):
    return func(*args, **kwargs)
```
