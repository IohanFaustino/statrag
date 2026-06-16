"""Ollama agent-delegation layer.

Delegate a task to an Ollama-cloud-brained agent the same way Claude Code's
``Agent`` tool delegates to a Claude subagent. Ollama is the brain (it decides
which tools to call via native function-calling); this package is the harness
(tool schemas + execution loop + transcript).

Why it exists: Claude Code subagents cannot run on ``ollama-cloud/*`` (errors
instantly, 0 tokens). This is the workaround so real Ollama agents execute tasks.
"""
from tools.ollama_agents.agent import OllamaAgent, AgentResult
from tools.ollama_agents.delegate import delegate

__all__ = ["OllamaAgent", "AgentResult", "delegate"]
