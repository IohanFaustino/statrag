"""Functional: a single conversation holds turns of different modes, each
persisted with its own metadata.turnMode."""
from __future__ import annotations

import pytest

from src.services.chat import api as chat_api
from src.services.chat.schemas._core import ChatRequest


@pytest.mark.asyncio
async def test_one_conversation_many_modes(monkeypatch):
    rows: list[dict] = []
    monkeypatch.setattr(chat_api.store, "append_message", lambda **kw: rows.append(kw))
    monkeypatch.setattr(chat_api.store, "get_messages", lambda _c: [])

    # Each turn's fake stream emits a meta echo + a structured payload tagged
    # with the requested mode, mimicking the real per-mode agents.
    async def _fake_stream(req, history=None):
        yield {"type": "meta", "mode": req.mode}
        yield {"type": "structured_output", "schema": f"{req.mode}-schema",
               "data": {"mode": req.mode}}

    monkeypatch.setattr(chat_api, "stream_chat", _fake_stream)

    conv = "conv-multi"
    for mode in ["tutor", "facilitate", "qa", "resume"]:
        req = ChatRequest(message=f"turn {mode}", mode=mode, model="gpt-4o",
                          conversationId=conv)
        async for _ in chat_api.chat_event_gen(req):
            pass

    assistant_rows = [r for r in rows if r["role"] == "assistant"]
    assert [r["metadata"]["turnMode"] for r in assistant_rows] == [
        "tutor", "facilitate", "qa", "resume"
    ]
    assert all(r["conversation_id"] == conv for r in rows)
