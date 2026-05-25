"""Detached, resumable chat-run manager (Common-ground §13).

A *run* is one assistant turn whose event source (the async generator from
:func:`src.services.chat.api.chat_event_gen`) is driven by a background
``asyncio.Task`` rather than by the HTTP/SSE connection.  The connection is
merely a *subscriber*: disconnecting (switching conversation, refreshing,
closing the tab, a network drop) no longer cancels generation, and the
assistant row is still persisted on completion.  Reconnecting replays any
events the client missed, keyed by a monotonic ``seq``.

Design contract (mirrored in ``docs/system/invariants.md``):

* Every buffered event carries a strictly increasing integer ``seq`` (1-based).
* At most **one active run per conversation** — :func:`start_run` returns the
  in-flight run instead of starting a duplicate turn.
* A detached run drains to completion and persists even with **zero**
  subscribers.
* Runs are process-local: a backend restart loses an in-flight run (persisted
  turns survive via SQLite).

Chinese wall: this module imports only the standard library.  The caller wires
in the event source via a factory, so ``runs`` knows nothing about the chat
pipeline.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

# Seconds a finished run is retained (for late/reconnecting subscribers) before
# it is garbage-collected to free the buffer.
RUN_TTL_SECONDS = 300

# Sentinel pushed to subscriber queues when the run finishes.
_DONE = object()


@dataclass
class _Run:
    conv_id: str
    events: list[dict] = field(default_factory=list)  # each has injected "seq"
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    done: bool = False
    finished_at: float | None = None
    task: asyncio.Task | None = None
    _gc_handle: asyncio.TimerHandle | None = None

    @property
    def seq(self) -> int:
        """Highest emitted sequence number (0 before any event)."""
        return self.events[-1]["seq"] if self.events else 0


_runs: dict[str, _Run] = {}


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


def get_run(conv_id: str) -> _Run | None:
    return _runs.get(conv_id)


def is_active(conv_id: str) -> bool:
    run = _runs.get(conv_id)
    return run is not None and not run.done


def status(conv_id: str) -> dict:
    """Lightweight status for the resume handshake."""
    run = _runs.get(conv_id)
    if run is None:
        return {"exists": False, "active": False, "done": False, "seq": 0}
    return {
        "exists": True,
        "active": not run.done,
        "done": run.done,
        "seq": run.seq,
    }


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def _drive(run: _Run, source: AsyncIterator[dict]) -> None:
    """Consume the event source, buffering + fanning out to subscribers.

    Always runs to completion regardless of subscribers — that is what makes
    generation (and its persistence side-effect) survive a client disconnect.
    """
    seq = 0
    try:
        async for ev in source:
            seq += 1
            ev2 = {**ev, "seq": seq}
            run.events.append(ev2)
            for q in list(run.subscribers):
                q.put_nowait(ev2)
    finally:
        run.done = True
        run.finished_at = time.monotonic()
        for q in list(run.subscribers):
            q.put_nowait(_DONE)
        _schedule_gc(run.conv_id)


def _schedule_gc(conv_id: str) -> None:
    run = _runs.get(conv_id)
    if run is None:
        return
    if run._gc_handle is not None:
        run._gc_handle.cancel()

    def _gc() -> None:
        cur = _runs.get(conv_id)
        # Only drop if it is still this finished run with no live subscribers.
        if cur is run and cur.done and not cur.subscribers:
            _runs.pop(conv_id, None)

    try:
        loop = asyncio.get_running_loop()
        run._gc_handle = loop.call_later(RUN_TTL_SECONDS, _gc)
    except RuntimeError:
        # No running loop (e.g. unit test driving _drive directly) — skip GC.
        run._gc_handle = None


def start_run(
    conv_id: str,
    source_factory: Callable[[], AsyncIterator[dict]],
) -> _Run:
    """Start (or reuse) a detached run for ``conv_id``.

    If an active run already exists for the conversation, it is returned
    unchanged — there is at most one active run per conversation.  A finished
    run is replaced by the new turn.
    """
    existing = _runs.get(conv_id)
    if existing is not None and not existing.done:
        return existing
    run = _Run(conv_id=conv_id)
    _runs[conv_id] = run
    run.task = asyncio.create_task(_drive(run, source_factory()))
    return run


async def subscribe(conv_id: str, after_seq: int = 0) -> AsyncIterator[dict]:
    """Yield events for ``conv_id`` with ``seq > after_seq``.

    Replays buffered events first, then streams live until the run finishes.
    Safe to call after the run is already done (pure replay).  Yields nothing
    if no run exists for the conversation.
    """
    run = _runs.get(conv_id)
    if run is None:
        return

    q: asyncio.Queue = asyncio.Queue()
    run.subscribers.add(q)
    try:
        last = after_seq
        # Replay the buffer snapshot. Events that arrive between registration
        # and this snapshot are also queued; the `seq <= last` guard below
        # dedups the overlap.
        for ev in list(run.events):
            if ev["seq"] > last:
                yield ev
                last = ev["seq"]

        if run.done:
            return

        while True:
            ev = await q.get()
            if ev is _DONE:
                return
            if ev["seq"] <= last:
                continue  # already replayed from the buffer snapshot
            yield ev
            last = ev["seq"]
    finally:
        run.subscribers.discard(q)
        # A run that finished while this was the last subscriber may now be GC-able.
        if run.done and not run.subscribers:
            _schedule_gc(conv_id)


def _reset_for_tests() -> None:
    """Clear all runs — test helper only."""
    for run in _runs.values():
        if run._gc_handle is not None:
            run._gc_handle.cancel()
    _runs.clear()
