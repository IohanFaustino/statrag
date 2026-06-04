"""Feasibility spike (throwaway): can deepagents run on our stack and drive our
models? Builds a trivial deep agent with the filesystem backend, drives it with an
OpenAI-compatible model aimed at the project's key, asks it to write+read a file
(the worker→synthesizer handoff primitive). Prints findings only.

Run: .venv/bin/python scripts/spike_deepagents.py
"""
from __future__ import annotations

import os
import traceback


def main() -> None:
    f = []
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    try:
        import deepagents
        f.append(f"OK import deepagents (version={getattr(deepagents, '__version__', '?')})")
    except Exception as e:  # noqa: BLE001
        f.append(f"FAIL import deepagents: {type(e).__name__}: {e}")
        print("\n".join(f))
        return

    # Build an OpenAI-compatible model pointed at our key (router uses OpenAI for nano).
    model = None
    try:
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(model="gpt-5.4-nano-2026-03-17", temperature=0,
                           api_key=os.environ.get("OPENAI_API_KEY"))
        f.append("OK ChatOpenAI(nano) constructed")
    except Exception as e:  # noqa: BLE001
        f.append(f"FAIL model construct: {type(e).__name__}: {e}")

    # Build a minimal deep agent with the virtual filesystem backend.
    try:
        from deepagents import create_deep_agent
        try:
            from deepagents.backends import FilesystemBackend
            backend = FilesystemBackend(root_dir=".", virtual_mode=True)
        except Exception as be:  # noqa: BLE001
            backend = None
            f.append(f"NOTE FilesystemBackend unavailable ({be}); using default backend")
        kwargs = {"model": model, "tools": [],
                  "system_prompt": "Write 'hello from worker' to brief.txt, then read it back and report the content."}
        if backend is not None:
            kwargs["backend"] = backend
        agent = create_deep_agent(**kwargs)
        f.append("OK create_deep_agent")
        result = agent.invoke({"messages": [{"role": "user", "content": "do it"}]},
                              config={"configurable": {"thread_id": "spike-1"}})
        msgs = result.get("messages", []) if isinstance(result, dict) else []
        last = msgs[-1].content if msgs else str(result)[:200]
        f.append(f"OK agent.invoke; result keys={list(result)[:6] if isinstance(result, dict) else type(result)}")
        f.append(f"   last message (truncated): {str(last)[:160]}")
    except Exception as e:  # noqa: BLE001
        f.append(f"FAIL agent run: {type(e).__name__}: {e}")
        f.append(traceback.format_exc()[:900])

    print("\n".join(f))


if __name__ == "__main__":
    main()
