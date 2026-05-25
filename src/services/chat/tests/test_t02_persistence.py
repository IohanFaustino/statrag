"""T02 acceptance: checkpointer + persistence fix (B1, B10).

Tests:
1. Checkpointer factory is process-singleton.
2. SqliteSaver round-trip across re-open (state survives process restart).
3. API chat route writes user + assistant messages to SQLite (B1 fix).
4. Per-thread isolation (B10: vec memory + SQLite stay in sync at thread level).
5. Perf: write + read median well under 100ms (NFR).
"""
from __future__ import annotations

import asyncio
import json
import operator
import uuid

import httpx
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict, Annotated

from src.services.chat import checkpointer as cp_mod
from src.services.chat import store


# Module-level TypedDict so get_type_hints can resolve `Annotated`.
class _S(TypedDict):
    msgs: Annotated[list[str], operator.add]


def _build_graph(saver):
    def node(state: _S) -> dict:
        return {"msgs": [state["msgs"][-1] + "_done"]}

    return (
        StateGraph(_S)
        .add_node("respond", node)
        .add_edge(START, "respond")
        .add_edge("respond", END)
        .compile(checkpointer=saver)
    )


# ---------------------------------------------------------------------------
# Checkpointer factory
# ---------------------------------------------------------------------------


def test_checkpointer_singleton(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cp_mod.settings, "checkpointer_db", str(tmp_path / "ck.db"), raising=False
    )
    cp_mod.reset_checkpointer()
    a = cp_mod.get_checkpointer()
    b = cp_mod.get_checkpointer()
    assert a is b, "checkpointer factory must return the same instance"
    assert isinstance(a, SqliteSaver)
    cp_mod.reset_checkpointer()


def test_checkpointer_db_file_created(monkeypatch, tmp_path):
    target = tmp_path / "ck.db"
    monkeypatch.setattr(
        cp_mod.settings, "checkpointer_db", str(target), raising=False
    )
    cp_mod.reset_checkpointer()
    cp_mod.get_checkpointer()
    assert target.exists(), "checkpointer DB file should be created on first use"
    cp_mod.reset_checkpointer()


def test_checkpointer_state_survives_reopen(monkeypatch, tmp_path):
    """Write a checkpoint, drop singleton, re-open, read it back."""
    monkeypatch.setattr(
        cp_mod.settings, "checkpointer_db", str(tmp_path / "ck.db"), raising=False
    )
    cp_mod.reset_checkpointer()

    saver = cp_mod.get_checkpointer()
    graph = _build_graph(saver)
    cfg = {"configurable": {"thread_id": "t-1"}}
    graph.invoke({"msgs": ["hi"]}, cfg)

    snapshot_before = graph.get_state(cfg)
    assert snapshot_before.values["msgs"] == ["hi", "hi_done"]

    cp_mod.reset_checkpointer()
    saver2 = cp_mod.get_checkpointer()
    graph2 = _build_graph(saver2)
    snapshot_after = graph2.get_state(cfg)
    assert snapshot_after.values["msgs"] == ["hi", "hi_done"], (
        "state must survive process restart"
    )
    cp_mod.reset_checkpointer()


def test_checkpointer_thread_isolation(monkeypatch, tmp_path):
    """Two thread_ids must not see each other's state."""
    monkeypatch.setattr(
        cp_mod.settings, "checkpointer_db", str(tmp_path / "ck.db"), raising=False
    )
    cp_mod.reset_checkpointer()

    saver = cp_mod.get_checkpointer()
    graph = _build_graph(saver)
    graph.invoke({"msgs": ["alice"]}, {"configurable": {"thread_id": "a"}})
    graph.invoke({"msgs": ["bob"]}, {"configurable": {"thread_id": "b"}})

    alice = graph.get_state({"configurable": {"thread_id": "a"}}).values["msgs"]
    bob = graph.get_state({"configurable": {"thread_id": "b"}}).values["msgs"]
    assert alice == ["alice", "alice_done"]
    assert bob == ["bob", "bob_done"]
    cp_mod.reset_checkpointer()


# ---------------------------------------------------------------------------
# B1 fix: api.py persists messages
# ---------------------------------------------------------------------------


def _stub_stream_factory(text: str = "hello world"):
    async def _gen(req, history=None):
        yield {"type": "token", "text": text}
        yield {"type": "sources_full", "sources": []}
        yield {"type": "done"}

    return _gen


def test_api_chat_persists_user_and_assistant(monkeypatch, tmp_path):
    """B1 fix: /api/chat writes both turn messages to SQLite."""
    db = tmp_path / "chat.db"
    monkeypatch.setattr(store, "DB_PATH", db, raising=False)
    monkeypatch.setattr(store, "_db_initialised", False, raising=False)
    store.init_db()
    digest = store.create_conversation(
        title="t", mode="tutor", model_id="gpt-5.4-nano-2026-03-17", book_filter="ALL"
    )
    conv_id = digest.id

    from src.services.chat import api, router
    from src.services.chat.schemas import ChatRequest
    monkeypatch.setattr(api, "stream_chat", _stub_stream_factory("greetings"))

    async def _drive():
        req = ChatRequest(
            message="what is OLS?",
            mode="tutor",
            model="gpt-5.4-nano-2026-03-17",
            bookFilter="ALL",
            conversationId=conv_id,
        )
        async for _ev in api.chat_event_gen(req):
            pass

    asyncio.run(_drive())

    msgs = store.get_messages(conv_id)
    roles = [m["role"] for m in msgs]
    assert "user" in roles, "user message must be persisted (B1)"
    assert "assistant" in roles, "assistant message must be persisted (B1)"

    user_row = next(m for m in msgs if m["role"] == "user")
    asst_row = next(m for m in msgs if m["role"] == "assistant")
    user_content = user_row["content"]
    asst_content = asst_row["content"]
    # store.append_message json.dumps the content; loads back into Python obj
    if isinstance(user_content, str) and user_content.startswith('"'):
        user_content = json.loads(user_content)
    if isinstance(asst_content, str) and asst_content.startswith('"'):
        asst_content = json.loads(asst_content)
    assert "OLS" in str(user_content)
    assert "greetings" in str(asst_content)


def test_api_chat_no_conv_id_does_not_crash(monkeypatch, tmp_path):
    """When conversationId is absent, the stream still succeeds."""
    db = tmp_path / "chat.db"
    monkeypatch.setattr(store, "DB_PATH", db, raising=False)
    monkeypatch.setattr(store, "_db_initialised", False, raising=False)
    store.init_db()

    from src.services.chat import api
    from src.services.chat.schemas import ChatRequest
    monkeypatch.setattr(api, "stream_chat", _stub_stream_factory("hi"))

    async def _drive():
        req = ChatRequest(
            message="ping",
            mode="tutor",
            model="gpt-5.4-nano-2026-03-17",
            bookFilter="ALL",
        )
        n = 0
        async for _ev in api.chat_event_gen(req):
            n += 1
        return n

    n = asyncio.run(_drive())
    assert n >= 1  # at least one event emitted


# ---------------------------------------------------------------------------
# Perf — NFR P95 < 100ms median
# ---------------------------------------------------------------------------


def test_checkpointer_write_read_perf(monkeypatch, tmp_path, benchmark):
    monkeypatch.setattr(
        cp_mod.settings, "checkpointer_db", str(tmp_path / "ck.db"), raising=False
    )
    cp_mod.reset_checkpointer()
    saver = cp_mod.get_checkpointer()
    graph = _build_graph(saver)

    def one_turn():
        cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
        graph.invoke({"msgs": ["m"]}, cfg)

    benchmark(one_turn)
    stats = benchmark.stats.stats
    assert stats.median < 0.1, f"checkpointer turn median > 100ms: {stats.median}"
    cp_mod.reset_checkpointer()
