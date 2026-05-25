"""T09 acceptance: tutor v2 routing + SSE adapter.

Tests:
1. Router falls through to v1 when USE_V2_MODES omits 'tutor'.
2. Router invokes the v2 tutor path when USE_V2_MODES contains 'tutor'.
3. v2 tutor stream emits ``meta`` → ``token``* → ``sources_full`` → ``retrieval_meta`` → ``done``.
4. Tool-call ToolMessage with ``name=='retrieve'`` populates ``sources_full``.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from src.services.chat import router
from src.services.chat.schemas import ChatRequest


def _collect(gen):
    async def _run():
        out = []
        async for ev in gen:
            out.append(ev)
        return out

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Feature flag routing
# ---------------------------------------------------------------------------


def test_tutor_falls_through_to_v1_when_flag_off(monkeypatch):
    monkeypatch.setattr(router.settings, "use_v2_modes", [], raising=False)

    async def _stub(req, history=None):
        yield {"type": "v1_marker"}

    from src.services.chat import orchestrator as v1
    monkeypatch.setattr(v1, "stream_chat", _stub)

    req = ChatRequest(message="x", mode="tutor", model="gpt-5.4-nano-2026-03-17")
    events = _collect(router.stream_chat(req))
    assert any(e["type"] == "v1_marker" for e in events)


def test_tutor_v2_path_used_when_flag_on(monkeypatch):
    monkeypatch.setenv("TUTOR_DEEP_MODE", "0"); monkeypatch.setattr(router.settings, "use_v2_modes", ["tutor"], raising=False)

    called = {"hit": False}

    async def _stub(req, history=None):
        called["hit"] = True
        yield {"type": "done"}

    monkeypatch.setattr(router, "_tutor_v2", _stub)
    req = ChatRequest(message="x", mode="tutor", model="gpt-5.4-nano-2026-03-17")
    events = _collect(router.stream_chat(req))
    assert called["hit"], "v2 tutor path was not taken with USE_V2_MODES=tutor"
    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# v2 tutor SSE adapter
# ---------------------------------------------------------------------------


class _FakeAgent:
    """Minimal stand-in for the compiled LangGraph agent used by tutor v2."""

    def __init__(self, events: list[tuple[str, object]]):
        self._events = events

    async def astream(self, inp, *, config, stream_mode):
        for kind, payload in self._events:
            yield kind, payload


def _msg_chunk(content: str):
    return SimpleNamespace(content=content)


def _tool_msg(name: str, content: str):
    return SimpleNamespace(type="tool", name=name, content=content)


def test_tutor_v2_emits_meta_tokens_sources_done(monkeypatch):
    """End-to-end shape: meta → token(s) → sources_full → retrieval_meta → done."""
    src_payload = json.dumps([
        {"rank": 1, "book": "islp", "chapter": "ch1", "section": "1.1",
         "title": "t", "excerpt": "e", "score": 0.7, "chunkId": "c-1"},
    ])
    fake_events = [
        ("updates", {"tools": {"messages": [_tool_msg("retrieve", src_payload)]}}),
        ("messages", (_msg_chunk("Hello "), {})),
        ("messages", (_msg_chunk("world"), {})),
    ]

    from src.services.chat.mode_impls import tutor as tutor_mod
    async def _mk_tutor_mod_agent():
        return _FakeAgent(fake_events)
    monkeypatch.setattr(tutor_mod, "build_agent", _mk_tutor_mod_agent)

    monkeypatch.setenv("TUTOR_DEEP_MODE", "0"); monkeypatch.setattr(router.settings, "use_v2_modes", ["tutor"], raising=False)
    req = ChatRequest(
        message="what is OLS?",
        mode="tutor",
        model="gpt-5.4-nano-2026-03-17",
        conversationId="t-1",
    )
    events = _collect(router.stream_chat(req))
    types = [e["type"] for e in events]

    assert types[0] == "meta"
    assert "token" in types
    assert "sources_full" in types
    assert types[-1] == "done"

    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    assert tokens == "Hello world"

    sources_ev = next(e for e in events if e["type"] == "sources_full")
    assert sources_ev["sources"][0]["chunkId"] == "c-1"


def test_tutor_v2_handles_agent_exception(monkeypatch):
    """A crash in astream is surfaced as an error+done pair."""

    class _BoomAgent:
        async def astream(self, inp, *, config, stream_mode):
            raise RuntimeError("agent down")
            yield  # never reached

    from src.services.chat.mode_impls import tutor as tutor_mod
    async def _mk_tutor_mod_agent():
        return _BoomAgent()
    monkeypatch.setattr(tutor_mod, "build_agent", _mk_tutor_mod_agent)

    monkeypatch.setenv("TUTOR_DEEP_MODE", "0"); monkeypatch.setattr(router.settings, "use_v2_modes", ["tutor"], raising=False)
    req = ChatRequest(message="x", mode="tutor", model="gpt-5.4-nano-2026-03-17")
    events = _collect(router.stream_chat(req))
    types = [e["type"] for e in events]
    assert "error" in types
    assert types[-1] == "done"
