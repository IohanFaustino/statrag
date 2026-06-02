"""Tests for the chapter-mode pipeline (fetch, resolve, map order)."""
from __future__ import annotations

from types import SimpleNamespace

import src.services.chat.retrieval as retrieval


class _FakePoint:
    # __slots__ without `score` makes attribute assignment raise, faithfully
    # mimicking the real immutable Qdrant `Record` returned by scroll() (a
    # frozen pydantic model with no `score` field). A plain mutable fake hid the
    # production crash where the code did `p.score = 0.0`.
    __slots__ = ("id", "payload")

    def __init__(self, pid, payload):
        self.id = pid
        self.payload = payload


def _payload(section_id, h2, page):
    return {
        "book_slug": "islp", "book_name": "ISLP", "chapter_id": "ch02",
        "section_id": section_id, "h2_path": h2, "h1": "Statistical Learning",
        "text": f"body of {section_id}", "page_from": page, "page_to": page,
        "authors": "James et al.", "year": 2021,
    }


def test_fetch_chapter_sections_sorted_by_page(monkeypatch):
    # Return points out of order; expect output sorted by (page_from, section_id).
    points = [
        _FakePoint("c", _payload("2.3", "2.3 | C", 30)),
        _FakePoint("a", _payload("2.1", "2.1 | A", 10)),
        _FakePoint("b", _payload("2.2", "2.2 | B", 20)),
    ]

    class _FakeClient:
        def scroll(self, **kwargs):
            return (points, None)

    monkeypatch.setattr(retrieval, "client", lambda: _FakeClient())
    monkeypatch.setattr(
        retrieval, "collections_for_books",
        lambda slugs: {"ml_dp_textbooks": ["islp"]},
    )

    out = retrieval.fetch_chapter_sections("islp", "ch02")
    assert [s.section for s in out] == ["A", "B", "C"]
    assert [s.chapter for s in out] == ["ch02", "ch02", "ch02"]


def test_model_for_prefers_stage_models():
    from src.services.chat.agents import chapter as ch
    from src.services.chat.schemas import ChatRequest
    req = ChatRequest(message="x", mode="resume", stageModels={"map": "gpt-4o-mini"})
    assert ch._model_for("map", req) == "gpt-4o-mini"
    # falls back to nano when unset
    req2 = ChatRequest(message="x", mode="resume")
    assert ch._model_for("map", req2) == ch.settings.openai_model_nano


import pytest


@pytest.mark.asyncio
async def test_parse_scope_extracts_chapter_and_subtopics(monkeypatch):
    from src.services.chat.agents import chapter as ch
    from src.services.chat.schemas import BookResolution, CatalogBook

    async def fake_resolve(message, *, selected_slugs, catalog, model=None):
        return BookResolution(book_slug="islp", book_confidence=1.0,
                              book_candidates=["islp"], chapter_id="ch02",
                              requested_subtopics=["the tradeoff"])

    monkeypatch.setattr(ch, "resolve_book", fake_resolve)
    monkeypatch.setattr(ch, "parse_catalog",
                        lambda: [CatalogBook(slug="islp", name="ISLP",
                                             authors_short="James et al.",
                                             field="ml_dp", chapters=["ch02"])])
    scope = await ch.parse_scope("explain the tradeoff in ch2", book_slugs=["islp"])
    assert scope.book_slug == "islp"
    assert scope.chapter_id == "ch02"
    assert scope.requested_subtopics == ["the tradeoff"]


@pytest.mark.asyncio
async def test_parse_scope_fail_open(monkeypatch):
    from src.services.chat.agents import chapter as ch
    from src.services.chat.schemas import BookResolution, CatalogBook

    # resolve_book itself fail-opens on LLM error; simulate that path
    async def fake_resolve_boom(message, *, selected_slugs, catalog, model=None):
        raise RuntimeError("llm down")

    monkeypatch.setattr(ch, "resolve_book", fake_resolve_boom)
    monkeypatch.setattr(ch, "parse_catalog",
                        lambda: [CatalogBook(slug="islp", name="ISLP",
                                             authors_short="James et al.",
                                             field="ml_dp", chapters=["ch02"])])
    # parse_scope wraps resolve_book; if resolve_book raises, the scope should still be returned
    # but since parse_scope is a thin wrapper, exceptions propagate. Test the real fallback:
    # Use a failing _scope._chat to exercise resolve_book's own fail-open path.
    import src.services.chat.agents._scope as _scope

    async def boom_chat(messages, *, model, max_tokens, temperature=0.0):
        raise RuntimeError("llm down")

    monkeypatch.setattr(_scope, "_chat", boom_chat)
    monkeypatch.setattr(ch, "resolve_book", _scope.resolve_book)
    scope = await ch.parse_scope("ch2 please", book_slugs=["islp"])
    # fail-open: single selected book used, no chapter, whole-chapter intent
    assert scope.book_slug == "islp"
    assert scope.requested_subtopics == []


def _src(section_id, h2):
    from src.services.chat.schemas import Source
    return Source(rank=1, book="islp", chapter="ch02", section=h2.split("|")[-1].strip(),
                  title=h2, excerpt="", score=0.0, chunkId=section_id, chunk="body",
                  page_from=1, page_to=1)


@pytest.mark.asyncio
async def test_resolve_empty_request_returns_whole_chapter(monkeypatch):
    from src.services.chat.agents import chapter as ch
    sections = [_src("2.1", "2.1 | A"), _src("2.2", "2.2 | B")]
    selected, resolution = await ch.resolve_subtopics([], sections)
    assert [s.chunkId for s in selected] == ["2.1", "2.2"]
    assert resolution == []  # whole-chapter: no per-name mapping


@pytest.mark.asyncio
async def test_resolve_substring_match_no_llm(monkeypatch):
    from src.services.chat.agents import chapter as ch

    async def boom(*a, **k):
        raise AssertionError("LLM must not be called for a substring hit")

    monkeypatch.setattr(ch, "_chat", boom)
    sections = [_src("2.1", "2.1 | Bias-Variance Trade-Off"), _src("2.2", "2.2 | Other")]
    selected, resolution = await ch.resolve_subtopics(["bias-variance"], sections)
    assert [s.chunkId for s in selected] == ["2.1"]
    assert resolution[0].matched_h2.endswith("Trade-Off")
    assert resolution[0].score >= 0.9


@pytest.mark.asyncio
async def test_resolve_fuzzy_falls_back_to_llm(monkeypatch):
    from src.services.chat.agents import chapter as ch

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return ('{"matches":[{"asked":"the tradeoff","section_id":"2.1",'
                '"matched_h2":"2.1 | Bias-Variance Trade-Off","score":0.78}]}')

    monkeypatch.setattr(ch, "_chat", fake_chat)
    sections = [_src("2.1", "2.1 | Bias-Variance Trade-Off"), _src("2.2", "2.2 | Other")]
    selected, resolution = await ch.resolve_subtopics(["the tradeoff"], sections)
    assert [s.chunkId for s in selected] == ["2.1"]
    assert resolution[0].asked == "the tradeoff"
    assert resolution[0].score == pytest.approx(0.78)


@pytest.mark.asyncio
async def test_map_sections_preserves_order_and_uses_resume_prompt(monkeypatch):
    from src.services.chat.agents import chapter as ch

    seen_prompts = []

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        seen_prompts.append(messages[0]["content"])
        return '{"body":"explained","citations":[],"math_blocks":["x^2"]}'

    monkeypatch.setattr(ch, "_chat", fake_chat)
    sections = [_src("2.1", "2.1 | A"), _src("2.2", "2.2 | B")]

    # map_sections now always uses CHAPTER_MAP_RESUME_PROMPT (facilitate was removed
    # from chapter.py; facilitate mode is handled by run_facilitate in facilitate.py).
    blocks_fac, _cites, math = await ch.map_sections(sections, mode="facilitate")
    assert [b.section_id for b in blocks_fac] == ["2.1", "2.2"]  # order preserved
    assert all("COMPRESS" in p for p in seen_prompts)  # always resume prompt now
    assert "x^2" in math  # math_blocks are threaded through

    seen_prompts.clear()
    blocks_res, _cites2, _math2 = await ch.map_sections(sections, mode="resume")
    assert all("COMPRESS" in p for p in seen_prompts)


@pytest.mark.asyncio
async def test_map_sections_fail_open_uses_excerpt(monkeypatch):
    from src.services.chat.agents import chapter as ch

    async def boom(*a, **k):
        raise RuntimeError("node down")

    monkeypatch.setattr(ch, "_chat", boom)
    sections = [_src("2.1", "2.1 | A")]
    sections[0].excerpt = "synopsis fallback"
    blocks, _cites, _math = await ch.map_sections(sections, mode="facilitate")
    assert blocks[0].body == "synopsis fallback"


@pytest.mark.asyncio
async def test_stitch_returns_intro_outro(monkeypatch):
    from src.services.chat.agents import chapter as ch
    from src.services.chat.schemas import ChapterBlock

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return '{"intro":"Covers A then B.","outro":"Together they explain X."}'

    monkeypatch.setattr(ch, "_chat", fake_chat)
    blocks = [ChapterBlock(h2_path="2.1 | A", section_id="2.1", body="a")]
    intro, outro = await ch.stitch(blocks)
    assert intro == "Covers A then B."
    assert outro == "Together they explain X."


@pytest.mark.asyncio
async def test_ground_fail_open(monkeypatch):
    from src.services.chat.agents import chapter as ch
    from src.services.chat.schemas import ChapterBlock

    async def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(ch, "_chat", boom)
    g = await ch.ground([ChapterBlock(h2_path="h", section_id="1", body="x")], [_src("1", "h")])
    assert g["ok"] is False and 0.0 <= g["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_run_chapter_emits_ordered_digest(monkeypatch):
    from src.services.chat.agents import chapter as ch
    from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest

    sections = [_src("2.1", "2.1 | A"), _src("2.2", "2.2 | B")]
    monkeypatch.setattr(ch, "fetch_chapter_sections", lambda b, c, **k: sections)

    # resolve_book returns a clean scope — bypasses _scope._chat entirely
    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="islp", book_confidence=1.0,
                              book_candidates=["islp"], chapter_id="ch02",
                              requested_subtopics=[])

    monkeypatch.setattr(ch, "resolve_book", fake_resolve)
    # catalog must include ch02 so maybe_clarify doesn't fire the chapter_missing gate
    monkeypatch.setattr(ch, "parse_catalog",
                        lambda: [CatalogBook(slug="islp", name="ISLP",
                                             authors_short="James et al.",
                                             field="ml_dp", chapters=["ch02"])])

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0):
        sys = messages[0]["content"]
        if "TEACH" in sys or "COMPRESS" in sys:
            return '{"body":"b","citations":[],"math_blocks":[]}'
        if "intro" in sys:
            return '{"intro":"i","outro":"o"}'
        return '{"ok":true,"unsupported":[],"confidence":0.9}'

    monkeypatch.setattr(ch, "_chat", fake_chat)

    req = ChatRequest(message="resume ch2", mode="resume", bookFilter=["islp"])
    events = [e async for e in ch.run_chapter(req)]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "meta" and kinds[-1] == "done"

    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "ChapterDigest"
    data = so["data"]
    assert data["mode"] == "resume"
    assert [b["section_id"] for b in data["blocks"]] == ["2.1", "2.2"]


@pytest.mark.asyncio
async def test_run_chapter_unknown_chapter_is_honest(monkeypatch):
    from src.services.chat.agents import chapter as ch
    from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest

    monkeypatch.setattr(ch, "fetch_chapter_sections", lambda b, c, **k: [])

    # resolve_book returns ch99 which IS in the catalog — so clarify gate is bypassed,
    # and the "Chapter not found" safety net fires because fetch returns [].
    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="islp", book_confidence=1.0,
                              book_candidates=["islp"], chapter_id="ch99",
                              requested_subtopics=[])

    monkeypatch.setattr(ch, "resolve_book", fake_resolve)
    # Include ch99 in catalog so chapter_missing gate does NOT fire
    monkeypatch.setattr(ch, "parse_catalog",
                        lambda: [CatalogBook(slug="islp", name="ISLP",
                                             authors_short="James et al.",
                                             field="ml_dp", chapters=["ch02", "ch99"])])
    req = ChatRequest(message="resume ch99", mode="resume", bookFilter=["islp"])
    events = [e async for e in ch.run_chapter(req)]
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["data"]["blocks"] == []
    assert so["data"]["citations"] == []
    assert events[-1]["type"] == "done"


def test_chapter_modes_registered():
    from src.services.chat.modes import ModeRegistry, register_all_modes
    register_all_modes()
    for mid in ("facilitate", "resume"):
        spec = ModeRegistry.get(mid)
        assert spec.arch == "multi"
        assert spec.output_schema.__name__ == "ChapterDigest"


@pytest.mark.asyncio
async def test_router_dispatches_chapter_modes(monkeypatch):
    import src.services.chat.router as router
    from src.services.chat.schemas import ChatRequest

    monkeypatch.setattr(router.settings, "use_v2_modes", ["tutor", "qa", "facilitate", "resume"])

    called = []

    async def fake_run_chapter(req):
        called.append(req.mode)
        yield {"type": "meta", "mode": req.mode, "_routed_via": "chapter_agent"}
        yield {"type": "done"}

    import src.services.chat.agents.chapter as chmod
    monkeypatch.setattr(chmod, "run_chapter", fake_run_chapter)

    req = ChatRequest(message="resume ch2", mode="resume", bookFilter=["islp"])
    events = [e async for e in router.stream_chat(req)]
    # Verify chapter agent was actually invoked (not v1 passthrough)
    assert called == ["resume"], "run_chapter must be called for mode=resume"
    assert any(e.get("_routed_via") == "chapter_agent" for e in events)
    assert events[-1]["type"] == "done"
