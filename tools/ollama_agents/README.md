# ollama_agents — delegate tasks to Ollama-cloud-brained agents

Delegate a task to an **Ollama-brained agent** the same way Claude Code's `Agent`
tool delegates to a Claude subagent. Ollama is the brain (native function-calling
decides each step); this package is the harness (tool schemas + execution loop).

**Why it exists:** Claude Code subagents cannot run on `ollama-cloud/*` — dispatch
errors instantly, 0 tokens. This Python layer is the workaround so a real Ollama
agent can read files, write code, run tests, and finish on its own.

## Use

```python
from tools.ollama_agents import delegate

res = delegate(
    "Create calc.py with add(a,b) and a passing pytest test_calc.py.",
    model="qwen3-coder-next",      # or deepseek-v4-pro / glm-5.1 / kimi-k2.7-code / minimax-m2.7
    root="/tmp/work",              # workspace the agent is confined to
    max_steps=30,
)
print(res.status, res.tool_calls, res.final_text)
```

CLI:

```bash
.venv/bin/python -m tools.ollama_agents.delegate --model glm-5.1 --root /tmp/work "TASK TEXT"
```

`AgentResult`: `status` (DONE/BLOCKED/MAX_STEPS), `final_text`, `steps`,
`tool_calls` (names in order), `transcript`.

## Tools the agent has

`read_file`, `write_file`, `edit_file` (unique-match), `run` (shell, workspace-cwd).
All paths confined to `root`. See `tools.py`.

## Auth (the gotcha)

Transport is the **native** Ollama endpoint, not OpenAI `/v1`:
`POST {OLLAMA_HOST}/api/chat` with `Authorization: Bearer {OLLAMA_API_KEY}`.

- The working pair lives in the repo **`.env`**: `OLLAMA_HOST=https://ollama.com`
  + the key. `backend.py` reads `.env` **first** — the shell environment may carry
  a different, non-matching `OLLAMA_HOST`/`OLLAMA_API_KEY` (e.g. `api.ollama.com`).
- The API key **contains a `.`** — never extract it with a regex that stops at
  punctuation (that truncation = silent 401).
- `/v1` (OpenAI-compat) returns 401 for these keys; use `/api/chat`.

## Tests

```bash
.venv/bin/python -m pytest tools/ollama_agents/tests -q              # offline (mocked)
OLLAMA_LIVE=1 .venv/bin/python -m pytest tools/ollama_agents/tests/test_live.py -q -s   # real Ollama, spends tokens
```

- `test_tools.py` — tool primitives + path-escape safety.
- `test_agent_loop.py` — the loop executes tool calls in order and stops (mocked backend).
- `test_live.py` — **parity proof**: an Ollama agent takes a TDD task to green,
  step-by-step like a subagent. Gated by `OLLAMA_LIVE=1`.
