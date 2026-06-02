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
