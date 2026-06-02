"""Run cancellation: runs.cancel halts an active detached run."""
from __future__ import annotations

import asyncio

import pytest

from src.services.chat import runs


@pytest.fixture(autouse=True)
def _clean_runs():
    runs._reset_for_tests()
    yield
    runs._reset_for_tests()


@pytest.mark.asyncio
async def test_cancel_active_run_stops_it():
    started = asyncio.Event()

    async def _source():
        yield {"type": "token", "text": "hello"}
        started.set()
        await asyncio.sleep(3600)
        yield {"type": "token", "text": "never"}

    runs.start_run("c1", _source)
    await asyncio.wait_for(started.wait(), timeout=2)

    assert runs.is_active("c1") is True
    assert runs.cancel("c1") is True

    # Poll until the run's _drive finally has run (bounded, ~0.5s max).
    for _ in range(50):
        if not runs.is_active("c1"):
            break
        await asyncio.sleep(0.01)
    assert runs.is_active("c1") is False


@pytest.mark.asyncio
async def test_cancel_unknown_run_returns_false():
    assert runs.cancel("nope") is False


def test_cancel_endpoint_unknown_conv_returns_false():
    from fastapi.testclient import TestClient

    from src.services.chat.api import app

    client = TestClient(app)
    r = client.post("/api/chat/does-not-exist/cancel")
    assert r.status_code == 200
    assert r.json() == {"cancelled": False}


@pytest.mark.asyncio
async def test_chat_event_gen_persists_partial_on_cancel(monkeypatch):
    """Cancelling mid-stream persists the partial assistant text with
    metadata {'stopped': True}."""
    import asyncio as _asyncio

    from src.services.chat import api as chat_api
    from src.services.chat.schemas._core import ChatRequest

    appended: list[dict] = []

    def _fake_append(**kwargs):
        appended.append(kwargs)

    monkeypatch.setattr(chat_api.store, "append_message", _fake_append)
    monkeypatch.setattr(chat_api.store, "get_messages", lambda _c: [])

    started = _asyncio.Event()

    async def _fake_stream(req, history=None):
        yield {"type": "token", "text": "par"}
        yield {"type": "token", "text": "tial"}
        started.set()
        await _asyncio.sleep(3600)

    monkeypatch.setattr(chat_api, "stream_chat", _fake_stream)

    req = ChatRequest(message="hi", mode="tutor", model="gpt-4o",
                      conversationId="conv-x")

    async def _consume():
        async for _ in chat_api.chat_event_gen(req):
            pass

    task = _asyncio.create_task(_consume())
    await _asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(_asyncio.CancelledError):
        await task

    assert appended, "partial was not persisted on cancel"
    row = appended[-1]
    assert row["role"] == "assistant"
    assert row["content"] == "partial"
    assert row["metadata"] == {"stopped": True}
