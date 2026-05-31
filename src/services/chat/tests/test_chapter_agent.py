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
