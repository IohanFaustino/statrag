"""Tests for the chapter confirm-gate (clarify event on ambiguity/miss)."""
from __future__ import annotations

import pytest
from src.services.chat.agents import chapter as chap
from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest

_CAT = [CatalogBook(slug="islp", name="ISL", authors_short="James et al.",
                    field="ml_dp", chapters=["ch02", "ch07"])]


async def _collect(req):
    return [ev async for ev in chap.run_chapter(req)]


@pytest.mark.asyncio
async def test_clarify_on_unknown_book(monkeypatch):
    monkeypatch.setattr(chap, "parse_catalog", lambda: _CAT)
    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="", book_confidence=0.0, book_candidates=[])
    monkeypatch.setattr(chap, "resolve_book", fake_resolve)
    req = ChatRequest(message="ch7 of Hansen probability", mode="resume", bookFilter=[])
    evs = await _collect(req)
    types = [e["type"] for e in evs]
    assert "clarify" in types
    clar = next(e for e in evs if e["type"] == "clarify")
    assert clar["reason"] in {"book_unknown", "book_ambiguous"}
    assert isinstance(clar["candidates"], list)
    assert types[-1] == "done"
    assert "structured_output" not in types


@pytest.mark.asyncio
async def test_clarify_on_chapter_missing(monkeypatch):
    monkeypatch.setattr(chap, "parse_catalog", lambda: _CAT)
    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="islp", book_confidence=0.95,
                              book_candidates=["islp"], chapter_id="ch99")
    monkeypatch.setattr(chap, "resolve_book", fake_resolve)
    req = ChatRequest(message="ch99 of ISL", mode="resume", bookFilter=["islp"])
    evs = await _collect(req)
    clar = next((e for e in evs if e["type"] == "clarify"), None)
    assert clar is not None and clar["reason"] == "chapter_missing"
    assert clar["chapter_guess"] == "ch99"


@pytest.mark.asyncio
async def test_no_clarify_kill_switch(monkeypatch):
    monkeypatch.setattr(chap, "_CHAPTER_CLARIFY", False)
    monkeypatch.setattr(chap, "parse_catalog", lambda: _CAT)
    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="", book_confidence=0.0, book_candidates=[])
    monkeypatch.setattr(chap, "resolve_book", fake_resolve)
    req = ChatRequest(message="??", mode="resume", bookFilter=[])
    evs = await _collect(req)
    assert "clarify" not in [e["type"] for e in evs]
