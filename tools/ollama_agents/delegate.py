"""delegate() — the public entrypoint, mirroring an Agent-tool dispatch.

    from tools.ollama_agents import delegate
    res = delegate("Create add.py with add(a,b) and a passing pytest.",
                   model="qwen3-coder-next", root=".")
    print(res.status, res.final_text)

CLI:
    .venv/bin/python -m tools.ollama_agents.delegate \
        --model qwen3-coder-next --root /tmp/work --max-steps 20 "TASK TEXT"
"""
from __future__ import annotations

import argparse
import sys

from tools.ollama_agents.agent import AgentResult, OllamaAgent

# Rotation pool (user: try more than deepseek/kimi). All confirmed tool-calling-capable.
MODELS = ["qwen3-coder-next", "deepseek-v4-pro", "glm-5.1",
          "kimi-k2.7-code", "minimax-m2.7"]


def delegate(task: str, model: str = "qwen3-coder-next", root: str = ".",
             max_steps: int = 30, system_prompt: str | None = None) -> AgentResult:
    agent = OllamaAgent(model, root, system_prompt) if system_prompt \
        else OllamaAgent(model, root)
    return agent.run(task, max_steps=max_steps)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Delegate a task to an Ollama agent.")
    ap.add_argument("task")
    ap.add_argument("--model", default="qwen3-coder-next")
    ap.add_argument("--root", default=".")
    ap.add_argument("--max-steps", type=int, default=30)
    a = ap.parse_args(argv)
    res = delegate(a.task, model=a.model, root=a.root, max_steps=a.max_steps)
    print(f"\n=== {res.status} ({res.steps} steps, tools: {', '.join(res.tool_calls) or 'none'}) ===")
    print(res.final_text)
    return 0 if res.status == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())
