import json
import pytest
from src.services.chat.schemas import ChatRequest, ExtensionDigest, ExtensionPoint, ExtensionFootnote
import src.services.chat.agents.extension_agents.runner as R


def _events(req):
    import asyncio
    async def _collect():
        return [e async for e in R.run_extension(req)]
    return asyncio.run(_collect())


def test_clarify_gate_stops_before_agent(monkeypatch):
    monkeypatch.setattr(R, "parse_catalog", lambda: [])
    async def _ascope(*a, **k):
        return {"type": "clarify", "options": ["a", "b"]}, None
    monkeypatch.setattr(R, "aresolve_scope_or_clarify", _ascope)
    monkeypatch.setattr(R, "build_extension_agent",
                        lambda **k: pytest.fail("agent built despite clarify"))
    evs = _events(ChatRequest(message="extend something vague", mode="extension"))
    assert any(e.get("type") == "clarify" for e in evs)
    assert evs[-1]["type"] == "done"


def test_happy_path_streams_points(monkeypatch):
    digest = ExtensionDigest(
        book="hansen-probability", chapter="ch07",
        points=[ExtensionPoint(title="LLN", curated_text="sample mean converges",
                               footnotes=[ExtensionFootnote(marker="1", body="$\\bar X\\to\\mu$",
                                                            source="ross §5.1", kind="corpus")])],
        unfilled_gaps=[])
    monkeypatch.setattr(R, "parse_catalog", lambda: [])
    async def _ascope(*a, **k):
        from src.services.chat.schemas import BookResolution
        return None, BookResolution(book_slug="hansen-probability", book_confidence=0.9,
                                    book_candidates=["hansen-probability"], chapter_id="ch07",
                                    requested_subtopics=[])
    monkeypatch.setattr(R, "aresolve_scope_or_clarify", _ascope)
    monkeypatch.setattr(R, "fetch_chapter_sections",
                        lambda **k: [{"section_id": "7.1", "h2_path": "Intro", "text": "t"}])
    monkeypatch.setattr(R, "_all_slugs", lambda catalog: ["hansen-probability", "ross-probability"])
    async def _run_round(agent, instruction, thread_id):
        return None, json.dumps(digest.model_dump()), [], 10, 20
    monkeypatch.setattr(R, "build_extension_agent", lambda **k: object())
    monkeypatch.setattr(R, "_warm_retrieval", lambda *a, **k: None)
    monkeypatch.setattr(R, "_run_round", _run_round)

    evs = _events(ChatRequest(message="extend hansen ch7", mode="extension"))
    types = [e["type"] for e in evs]
    assert "structured_output" in types
    so = next(e for e in evs if e["type"] == "structured_output")
    assert so["schema"] == "ExtensionDigest"
    assert so["data"]["points"][0]["title"] == "LLN"
    assert evs[-1]["type"] == "done"


def test_round_loop_caps(monkeypatch):
    monkeypatch.setattr(R, "parse_catalog", lambda: [])
    async def _ascope(*a, **k):
        from src.services.chat.schemas import BookResolution
        return None, BookResolution(book_slug="b", book_confidence=0.9, book_candidates=["b"],
                                    chapter_id="ch01", requested_subtopics=[])
    monkeypatch.setattr(R, "aresolve_scope_or_clarify", _ascope)
    monkeypatch.setattr(R, "fetch_chapter_sections", lambda **k: [{"section_id": "1", "h2_path": "i", "text": "t"}])
    monkeypatch.setattr(R, "_all_slugs", lambda catalog: ["b"])
    monkeypatch.setattr(R, "build_extension_agent", lambda **k: object())
    monkeypatch.setattr(R, "_warm_retrieval", lambda *a, **k: None)
    calls = {"n": 0}
    empty = json.dumps(ExtensionDigest(book="b", chapter="ch01", points=[], unfilled_gaps=["q"]).model_dump())
    async def _run_round(agent, instruction, thread_id):
        calls["n"] += 1
        return None, empty, ["q"], 1, 1
    monkeypatch.setattr(R, "_run_round", _run_round)

    evs = _events(ChatRequest(message="extend b ch1", mode="extension", extensionMaxRounds=2))
    assert calls["n"] == 2
    so = next(e for e in evs if e["type"] == "structured_output")
    assert so["data"]["unfilled_gaps"] == ["q"]
