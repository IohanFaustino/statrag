"""Tests for the detached, resumable run manager (§13, ``runs.py``)."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from src.services.chat import runs


@pytest.fixture(autouse=True)
def _clean_runs():
    runs._reset_for_tests()
    yield
    runs._reset_for_tests()


def _source(items: list[dict], *, delay: float = 0.0):
    async def gen() -> AsyncIterator[dict]:
        for it in items:
            if delay:
                await asyncio.sleep(delay)
            yield it

    return gen


async def _collect(conv_id: str, after: int = 0) -> list[dict]:
    out: list[dict] = []
    async for ev in runs.subscribe(conv_id, after_seq=after):
        out.append(ev)
    return out


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seq_is_monotonic_and_buffered():
    items = [{"type": "token", "text": "a"}, {"type": "token", "text": "b"}, {"type": "done"}]
    run = runs.start_run("c1", _source(items))
    await run.task  # drive to completion
    events = await _collect("c1")
    assert [e["seq"] for e in events] == [1, 2, 3]
    assert [e["type"] for e in events] == ["token", "token", "done"]


@pytest.mark.asyncio
async def test_persists_with_zero_subscribers():
    seen: list[str] = []

    def src():
        async def gen() -> AsyncIterator[dict]:
            for t in ("x", "y"):
                seen.append(t)
                yield {"type": "token", "text": t}
            yield {"type": "done"}

        return gen()

    run = runs.start_run("c2", src)
    await run.task  # no subscriber ever attached
    assert seen == ["x", "y"]  # source fully drained
    assert run.done and run.seq == 3


@pytest.mark.asyncio
async def test_resume_after_seq_skips_replayed():
    items = [{"type": "token", "text": "a"}, {"type": "token", "text": "b"}, {"type": "done"}]
    run = runs.start_run("c3", _source(items))
    await run.task
    tail = await _collect("c3", after=2)
    assert [e["seq"] for e in tail] == [3]


@pytest.mark.asyncio
async def test_two_subscribers_get_identical_streams():
    items = [{"type": "token", "text": str(i)} for i in range(5)] + [{"type": "done"}]
    runs.start_run("c4", _source(items, delay=0.005))
    a, b = await asyncio.gather(_collect("c4"), _collect("c4"))
    assert a == b
    assert [e["seq"] for e in a] == [1, 2, 3, 4, 5, 6]


@pytest.mark.asyncio
async def test_live_subscriber_receives_then_terminates():
    items = [{"type": "token", "text": "a"}, {"type": "token", "text": "b"}, {"type": "done"}]
    runs.start_run("c5", _source(items, delay=0.01))
    # Subscribe while the run is still in flight.
    events = await _collect("c5")
    assert [e["type"] for e in events] == ["token", "token", "done"]


@pytest.mark.asyncio
async def test_at_most_one_active_run_per_conversation():
    slow = _source([{"type": "token", "text": "a"}, {"type": "done"}], delay=0.05)
    r1 = runs.start_run("c6", slow)
    r2 = runs.start_run("c6", _source([{"type": "done"}]))  # ignored while active
    assert r1 is r2
    await r1.task
    # Finished run is replaced by a new turn.
    r3 = runs.start_run("c6", _source([{"type": "done"}]))
    assert r3 is not r1
    await r3.task


@pytest.mark.asyncio
async def test_status_handshake():
    assert runs.status("nope") == {"exists": False, "active": False, "done": False, "seq": 0}
    run = runs.start_run("c7", _source([{"type": "token", "text": "a"}, {"type": "done"}]))
    await run.task
    st = runs.status("c7")
    assert st["exists"] and st["done"] and not st["active"] and st["seq"] == 2


@pytest.mark.asyncio
async def test_subscribe_unknown_conversation_yields_nothing():
    assert await _collect("ghost") == []
