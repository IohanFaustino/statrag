# deepagents feasibility spike — findings (2026-06-04)

**Verdict: `FEASIBLE` — Plan B (L2/L3 deepagents conversion) can proceed.**

## What was tested

`scripts/spike_deepagents.py`: install deepagents, construct an OpenAI-compatible
model aimed at the project key, build a `create_deep_agent` with the virtual
filesystem backend, and ask it to write+read a file (the worker→synthesizer handoff
primitive).

## Results

```
OK import deepagents (version=0.6.8)
OK ChatOpenAI(nano) constructed
OK create_deep_agent
OK agent.invoke; result keys=['messages', 'files']
   last message (truncated): hello from worker
```

- **Imports + runs** on the current stack.
- **Drives our nano model** via `langchain_openai.ChatOpenAI(model="gpt-5.4-nano-2026-03-17", api_key=...)` — i.e. our OpenAI-routed models work directly. (Non-OpenAI router models — qwen/gemini — would need their LangChain integrations or a `base_url` override; not needed for the ablation, which holds the model at nano.)
- **Virtual filesystem confirmed:** `agent.invoke(...)` returns state with a **`files`** key; the agent wrote `brief.txt` and read it back. This is the structured **worker→synthesizer context channel** L2 needs (replace `_format_author_briefs` string-stuffing with per-author brief files the synthesizer reads).
- **Subagents** (`subagents=[...]`) + `SubAgentMiddleware` available for L3 (one subagent per author).

## Dependency impact

`deepagents==0.6.8` pulled minor bumps: `langchain 1.3.1→1.3.4`, `langgraph 1.2.0→1.2.4`
(both within the `<2.0` pins) plus transitive `anthropic`, `langchain-anthropic`,
`langchain-google-genai`. **No major-version conflict.** The full chat suite stayed
green at the bumped versions (641 passed) and `pip check` reported no broken
requirements. The bumped langchain/langgraph were left in place (compatible);
deepagents itself was **uninstalled** after the spike to keep Plan A's venv clean —
Plan B reinstalls it and adds it to `requirements.txt` only when a level ships.

## API for Plan B

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_openai import ChatOpenAI

agent = create_deep_agent(
    model=ChatOpenAI(model="gpt-5.4-nano-2026-03-17", temperature=0, api_key=...),
    tools=[],
    system_prompt="...",
    backend=FilesystemBackend(root_dir=".", virtual_mode=True),  # L2 shared FS
    subagents=[...],                                             # L3 per-author
)
result = agent.invoke({"messages": [...]}, config={"configurable": {"thread_id": "..."}})
# result["files"] holds the virtual filesystem; result["messages"] the output.
```

## Recommended Plan B path

- **L2** = synthesizer reads per-author brief **files** from the deepagents virtual
  FS instead of the flattened `_format_author_briefs` string. Model held at nano.
- **L3** = `create_deep_agent` with one **subagent per author** + planning, replacing
  the hand-rolled orchestrator.
- Both flag-gated (`TUTOR_OW_HARNESS=2|3`), L0 fallback, measured against the L0
  baseline + context-fidelity metric from Plan A.
