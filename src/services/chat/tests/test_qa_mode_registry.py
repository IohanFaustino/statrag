"""qa mode registration + router dispatch tests."""
from __future__ import annotations

import pytest

from src.services.chat.schemas import ChatRequest


def test_qa_mode_registered():
    from src.services.chat.modes import ModeRegistry
    spec = ModeRegistry.get("qa")
    assert spec.id == "qa"
    assert spec.arch == "multi"


@pytest.mark.asyncio
async def test_router_dispatches_qa_to_run_qa(monkeypatch):
    from src.services.chat import router as r
    from src.services.chat.agents import qa

    async def fake_run_qa(req):
        yield {"type": "meta", "mode": "qa"}
        yield {"type": "done"}

    monkeypatch.setattr(qa, "run_qa", fake_run_qa)
    # force v2 enabled for qa regardless of env
    monkeypatch.setattr(r, "_v2_enabled_for", lambda mode_id: True)

    req = ChatRequest(message="x", mode="qa")
    events = [ev async for ev in r.stream_chat(req)]
    assert events[0]["mode"] == "qa"
    assert events[-1]["type"] == "done"
