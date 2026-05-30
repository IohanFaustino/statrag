# code:agentic_patterns:ch14 — Use Case: A Multi-Agent System for Loan Processing

book: Agentic Architectural Patterns for Building Multi-Agent Systems
slug: agentic_patterns
chapter: ch14
chapter_title: Use Case: A Multi-Agent System for Loan Processing
repo: https://github.com/PacktPublishing/Agentic-Architectural-Patterns-for-Building-Multi-Agent-Systems (branch main)
folder: Chapter_14

## Summary
Chapter 14 expands the ch13 single-agent design into a Multi-Agent System (MAS) using Google ADK, replacing the monolithic `LlmAgent` with a FCoT-powered Orchestrator Agent that delegates to four specialist sub-agents: `document_validator`, `credit_checker`, `risk_assessor`, and `compliance_checker`. Each sub-agent is an `LlmAgent` with a single scoped `FunctionTool` and a strict task instruction that errors if required input is missing, enforcing clear separation of concerns. The orchestrator uses `AgentTool`-wrapped sub-agents and `BuiltInPlanner` to sequence the pipeline; all inter-agent calls are protected by the same `tenacity` exponential-backoff + `ratelimit` throttling pattern from ch13. Three borrower scenarios (happy path CUST-12345 score 810, high-risk CUST-55555 score 680, no-history CUST-00700) demonstrate orchestrator-level branching logic.

## Libraries & frameworks
getpass, google, json, os, random, ratelimit, tenacity, time, uuid

## Models & APIs
`gemini-2.5-flash` (and `gemini-3-flash` as a placeholder constant) via Google GenAI SDK (`google-adk`, `google.genai`, `google.api_core`); Google API Key via `GOOGLE_API_KEY` env var; ADK `BuiltInPlanner` with `ThinkingConfig`.

## Concepts / patterns
Multi-agent system (MAS) with orchestrator-workers pattern; agent-to-agent (A2A) delegation via ADK `AgentTool`; specialist sub-agent isolation (one tool per agent, strict input contracts); FCoT orchestrator prompt (Recap → Reason → Verify); `BuiltInPlanner` for orchestrator-level task sequencing; tool use with `FunctionTool` per sub-agent; rate limiting (`ratelimit`) + exponential backoff (`tenacity`) for enterprise robustness; multi-scenario branching (approval, high-risk denial, no-history denial); separation of concerns vs. ch13 monolith; loan-to-income ratio and credit-score thresholds as deterministic policy rules.

## Files
- Chapter_14_Multi_Agent.ipynb — Builds a Google ADK Multi-Agent System where a FCoT Orchestrator Agent delegates loan-processing steps to four scoped specialist sub-agents via `AgentTool`, demonstrating orchestrator-workers separation of concerns. (py)

## Code entities
- Chapter_14_Multi_Agent.ipynb: validate_document_fields, query_credit_bureau_api, calculate_risk_score, check_lending_compliance, is_rate_limit_error, start_agent_run, call_agent

## Key snippets

```python
# Specialist sub-agent with a single scoped tool and strict input contract
credit_check_instructions = """
You are a Credit Check Agent.
Your ONLY task is to call the `query_credit_bureau_api` tool.
**INPUT REQUIREMENT:** You must receive the applicant's 'customer_id'.
If the 'customer_id' is not provided, respond with an error: 'ERROR: Missing customer_id input.'
"""
credit_checker = LlmAgent(
    model="gemini-2.5-flash",
    name="credit_checker",
    instruction=credit_check_instructions,
    tools=[FunctionTool(func=query_credit_bureau_api)]
)
```

```python
# Orchestrator wraps sub-agents as AgentTools for A2A delegation
orchestrator = LlmAgent(
    model="gemini-2.5-flash",
    name="LoanOrchestrator",
    instruction=orchestrator_instructions,  # FCoT prompt
    planner=BuiltInPlanner(thinking_config=ThinkingConfig(include_thoughts=True, thinking_budget=1024)),
    tools=[
        AgentTool(agent=document_validator),
        AgentTool(agent=credit_checker),
        AgentTool(agent=risk_assessor),
        AgentTool(agent=compliance_checker),
    ]
)
```

```python
# Risk tool: loan-to-income ratio + credit score thresholds
def calculate_risk_score(loan_amount: int, income: str, credit_score: int) -> str:
    income_value = int(''.join(filter(str.isdigit, income)))
    annual_income = income_value * 12 if "month" in income.lower() else income_value
    risk_score = 1
    if credit_score < 650: risk_score += 4
    elif credit_score < 720: risk_score += 2
    if loan_amount / annual_income > 0.8: risk_score += 5
    elif loan_amount / annual_income > 0.5: risk_score += 2
    return json.dumps({"risk_score": min(risk_score, 10)})
```
