"""T10 acceptance: 7 remaining single-agent modes routed through structured adapter."""
from __future__ import annotations

import asyncio
import json
import sys
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


class _FakeAgent:
    def __init__(self, events):
        self._events = events

    async def astream(self, inp, *, config, stream_mode):
        for kind, payload in self._events:
            yield kind, payload


def _tool_msg(name: str, content: str):
    return SimpleNamespace(type="tool", name=name, content=content)


def _structured_dict(payload: dict):
    return SimpleNamespace(model_dump=lambda: payload)


# ---------------------------------------------------------------------------
# Registry is complete + factory paths resolve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode_id", list(router._STRUCTURED_V2_MODES.keys()))
def test_structured_mode_factory_imports(mode_id):
    import importlib
    factory_path, schema_name = router._STRUCTURED_V2_MODES[mode_id]
    mod = importlib.import_module(factory_path)
    assert hasattr(mod, "build_agent"), f"{factory_path} missing build_agent"
    assert isinstance(schema_name, str) and schema_name


# ---------------------------------------------------------------------------
# Quiz mode end-to-end via fake agent
# ---------------------------------------------------------------------------


def test_quiz_v2_structured_output_event(monkeypatch):
    src_payload = json.dumps([{"rank": 1, "book": "x", "chapter": "c", "section": "s",
                                 "title": "t", "excerpt": "e", "score": 0.5, "chunkId": "c-1"}])
    schema_payload = {"questions": [{
        "stem": "Q?", "options": ["a", "b"], "answer_idx": 0,
        "rubric": "r", "source": {"book": "x", "chapter": "c", "section": "s"},
        "difficulty": "easy", "self_check_passed": True,
    }]}
    fake_events = [
        ("messages", (SimpleNamespace(content="streaming "), {})),
        ("updates", {"tools": {"messages": [_tool_msg("retrieve", src_payload)]}}),
        ("messages", (SimpleNamespace(content="output"), {})),
        ("updates", {"final": {"structured_response": _structured_dict(schema_payload)}}),
    ]

    from src.services.chat.mode_impls import quiz as quiz_mod
    async def _mk_quiz_mod_agent():
        return _FakeAgent(fake_events)
    monkeypatch.setattr(quiz_mod, "build_agent", _mk_quiz_mod_agent)

    monkeypatch.setattr(router.settings, "use_v2_modes", ["quiz"], raising=False)
    req = ChatRequest(message="quiz me", mode="quiz", model="gpt-5.4-nano-2026-03-17")
    events = _collect(router.stream_chat(req))
    types = [e["type"] for e in events]

    assert "meta" in types
    assert "structured_output" in types
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "Quiz"
    assert so["data"]["questions"][0]["stem"] == "Q?"
    assert "sources_full" in types
    assert types[-1] == "done"


# ---------------------------------------------------------------------------
# Compare mode collects per-book sources
# ---------------------------------------------------------------------------


def test_compare_v2_collects_per_book_sources(monkeypatch):
    per_book = {
        "a": [{"rank": 1, "book": "a", "chapter": "c1", "section": "s1",
                "title": "A", "excerpt": "", "score": 0.5, "chunkId": "a-1"}],
        "b": [{"rank": 1, "book": "b", "chapter": "c1", "section": "s1",
                "title": "B", "excerpt": "", "score": 0.5, "chunkId": "b-1"}],
    }
    schema_payload = {
        "books": [
            {"book": "a", "text": "A treats it as X", "citations": []},
            {"book": "b", "text": "B treats it as Y", "citations": []},
        ],
        "synthesis": "Both books agree on Z.",
        "divergences": [],
        "citations": [],
    }
    fake_events = [
        ("updates", {"tools": {"messages": [_tool_msg("retrieve_per_book", json.dumps(per_book))]}}),
        ("updates", {"final": {"structured_response": _structured_dict(schema_payload)}}),
    ]

    from src.services.chat.mode_impls import compare as compare_mod
    async def _mk_compare_mod_agent():
        return _FakeAgent(fake_events)
    monkeypatch.setattr(compare_mod, "build_agent", _mk_compare_mod_agent)

    monkeypatch.setattr(router.settings, "use_v2_modes", ["compare"], raising=False)
    req = ChatRequest(message="compare X", mode="compare", model="gpt-5.4-nano-2026-03-17")
    events = _collect(router.stream_chat(req))
    src_ev = next(e for e in events if e["type"] == "sources_full")
    chunk_ids = {s["chunkId"] for s in src_ev["sources"]}
    assert chunk_ids == {"a-1", "b-1"}


# ---------------------------------------------------------------------------
# Figures mode captures figures_full
# ---------------------------------------------------------------------------


def test_figures_v2_emits_figures_full(monkeypatch):
    figs = [{"ref": "f1", "book": "x", "chapter": "c", "caption": "cap", "chart": "https://x.png"}]
    fake_events = [
        ("updates", {"tools": {"messages": [_tool_msg("retrieve_figures", json.dumps(figs))]}}),
    ]

    from src.services.chat.mode_impls import figures as fig_mod
    async def _mk_fig_mod_agent():
        return _FakeAgent(fake_events)
    monkeypatch.setattr(fig_mod, "build_agent", _mk_fig_mod_agent)

    monkeypatch.setattr(router.settings, "use_v2_modes", ["figures"], raising=False)
    req = ChatRequest(message="show me", mode="figures", model="gpt-5.4-nano-2026-03-17")
    events = _collect(router.stream_chat(req))
    ff = next(e for e in events if e["type"] == "figures_full")
    assert ff["figures"][0]["ref"] == "f1"


# ---------------------------------------------------------------------------
# Each mode's build_structured_agent call shape is valid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode_id", [
    "compare", "figures", "quiz", "navigate", "annotate", "math", "roadmap",
])
def test_structured_modes_have_response_format_schema(mode_id):
    """Each mode declares a non-None Pydantic schema."""
    import importlib
    factory_path, schema_name = router._STRUCTURED_V2_MODES[mode_id]
    mod = importlib.import_module(factory_path)
    # The build_agent function references the schema via response_format kwarg;
    # we check the module imports a schema named per the registry.
    src = mod.__loader__.get_source(mod.__name__) or ""
    assert schema_name in src, f"{factory_path} does not reference {schema_name}"
