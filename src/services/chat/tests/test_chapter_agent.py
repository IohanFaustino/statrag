"""Tests for the chapter-mode pipeline (fetch, resolve, map order)."""
from __future__ import annotations

from types import SimpleNamespace

import src.services.chat.retrieval as retrieval


class _FakePoint:
    def __init__(self, pid, payload):
        self.id = pid
        self.payload = payload
        self.score = 0.0


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

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0):
        return ('{"book_slug":"islp","chapter_id":"ch02",'
                '"requested_subtopics":["the tradeoff"]}')

    monkeypatch.setattr(ch, "_chat", fake_chat)
    scope = await ch.parse_scope("explain the tradeoff in ch2", book_slugs=["islp"])
    assert scope.book_slug == "islp"
    assert scope.chapter_id == "ch02"
    assert scope.requested_subtopics == ["the tradeoff"]


@pytest.mark.asyncio
async def test_parse_scope_fail_open(monkeypatch):
    from src.services.chat.agents import chapter as ch

    async def boom(messages, *, model, max_tokens, temperature=0.0):
        raise RuntimeError("llm down")

    monkeypatch.setattr(ch, "_chat", boom)
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

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0):
        return ('{"matches":[{"asked":"the tradeoff","section_id":"2.1",'
                '"matched_h2":"2.1 | Bias-Variance Trade-Off","score":0.78}]}')

    monkeypatch.setattr(ch, "_chat", fake_chat)
    sections = [_src("2.1", "2.1 | Bias-Variance Trade-Off"), _src("2.2", "2.2 | Other")]
    selected, resolution = await ch.resolve_subtopics(["the tradeoff"], sections)
    assert [s.chunkId for s in selected] == ["2.1"]
    assert resolution[0].asked == "the tradeoff"
    assert resolution[0].score == pytest.approx(0.78)
