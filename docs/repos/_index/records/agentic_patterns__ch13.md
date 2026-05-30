# code:agentic_patterns:ch13 — Use Case: A Single Agent for Loan Processing

book: Agentic Architectural Patterns for Building Multi-Agent Systems
slug: agentic_patterns
chapter: ch13
chapter_title: Use Case: A Single Agent for Loan Processing
repo: https://github.com/PacktPublishing/Agentic-Architectural-Patterns-for-Building-Multi-Agent-Systems (branch main)
folder: Chapter_13

## Summary
Chapter 13 implements a single-agent loan origination pipeline using the Google Agent Development Kit (ADK) and Gemini 2.5 Flash. One `LlmAgent` named `LoanProcessingAgent` orchestrates four `FunctionTool` callables — document validation, credit bureau lookup, risk assessment, and compliance check — driven by a Fractal Chain-of-Thought (FCoT) system prompt that enforces a "Recap → Reason → Verify" loop across three iterations. The `BuiltInPlanner` with a 1024-token `ThinkingConfig` lets the agent autonomously sequence tools, and exponential-backoff retry logic via `tenacity` plus `ratelimit` rate-capping protect against Gemini API quota exhaustion. The chapter demonstrates the happy-path approval and the high-risk denial branches for borrower profiles differentiated by customer ID.

## Libraries & frameworks
getpass, google, os, random, ratelimit, tenacity, time, uuid

## Models & APIs
`gemini-2.5-flash` via Google GenAI SDK (`google-adk`, `google.genai`); Google API Key via `GOOGLE_API_KEY` env var; `ThinkingConfig` (thinking budget 1024 tokens) passed to `BuiltInPlanner`.

## Concepts / patterns
Single-agent orchestration; tool use via ADK `FunctionTool` and `LlmAgent`; Fractal Chain-of-Thought (FCoT) prompting pattern (Recap → Reason → Verify loop, N=3 iterations); `BuiltInPlanner` with `ThinkingConfig` for autonomous task sequencing; rate limiting (`ratelimit` `@limits`) + exponential backoff (`tenacity` `@retry`) for enterprise robustness; branching logic (happy-path approval vs. high-risk denial); `InMemorySessionService` for stateful ADK runner sessions; no hallucination / human-in-the-loop deferral policy encoded in system prompt.

## Files
- Chapter_13_Agent.ipynb — Implements a single `LlmAgent` (Google ADK + Gemini 2.5 Flash) with four `FunctionTool` callables and a FCoT system prompt to autonomously evaluate loan applications end-to-end. (py)

## Code entities
- Chapter_13_Agent.ipynb: validate_document, run_credit_check, assess_risk, check_compliance, is_rate_limit_error, start_agent_run, call_agent

## Key snippets

```python
# FCoT BuiltInPlanner with ThinkingConfig
thinking_config = ThinkingConfig(include_thoughts=True, thinking_budget=1024)
planner = BuiltInPlanner(thinking_config=thinking_config)

agent = LlmAgent(
    model="gemini-2.5-flash",
    name="LoanProcessingAgent",
    instruction=agent_instructions,  # FCoT: Recap→Reason→Verify x3
    planner=planner,
    tools=[validate_document_tool, run_credit_check_tool, assess_risk_tool, check_compliance_tool]
)
```

```python
# Robust runner: rate-limited + exponential-backoff retries
@sleep_and_retry
@limits(calls=15, period=60)
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception(is_rate_limit_error),
    reraise=True
)
def start_agent_run(runner, user_id, session_id, content):
    return runner.run(user_id=user_id, session_id=session_id, new_message=content)
```

```python
# Tool example: credit check returns score driving risk/denial branching
def run_credit_check(borrower_id: str) -> dict:
    if borrower_id == "Borrower-400":
        return {"credit_score": 450, "report_summary": "Credit history is compromised."}
    score = random.randint(750, 850)
    return {"credit_score": score, "report_summary": "Credit history is clean."}
```
