from src.services.chat.books import parse_catalog
from src.services.chat.schemas import CatalogBook


def test_parse_catalog_returns_books_with_chapters():
    cat = parse_catalog()
    assert isinstance(cat, list)
    assert cat and all(isinstance(b, CatalogBook) for b in cat)
    b = cat[0]
    assert b.slug and b.name
    assert all(c.startswith("ch") for c in b.chapters)
    assert b.chapters == sorted(b.chapters)


from src.services.chat.agents._scope import expand_section_refs


def test_expand_section_refs_range():
    assert expand_section_refs("sections 7.2 up to 7.4") == ["7.2", "7.3", "7.4"]

def test_expand_section_refs_list_and_dash():
    assert expand_section_refs("7.2, 7.3 and 7.5") == ["7.2", "7.3", "7.5"]
    assert expand_section_refs("7.2-7.4") == ["7.2", "7.3", "7.4"]

def test_expand_section_refs_none():
    assert expand_section_refs("teach me about variance") == []


# ---------------------------------------------------------------------------
# Task 3 — resolve_book catalog-in-prompt resolver
# ---------------------------------------------------------------------------

import json as _json
import pytest
from src.services.chat.agents import _scope
from src.services.chat.schemas import CatalogBook

_CAT = [
    CatalogBook(slug="islp", name="An Introduction to Statistical Learning",
                authors_short="James et al.", field="ml_dp",
                chapters=["ch01", "ch02", "ch07"]),
    CatalogBook(slug="hansen-econometrics", name="Econometrics",
                authors_short="Hansen", field="econometrics", chapters=["ch01"]),
]


@pytest.mark.asyncio
async def test_resolve_book_confident(monkeypatch):
    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return _json.dumps({
            "book_slug": "islp", "book_confidence": 0.92,
            "book_candidates": ["islp"], "chapter_id": "ch07",
            "requested_subtopics": [],
        })
    monkeypatch.setattr(_scope, "_chat", fake_chat)
    r = await _scope.resolve_book("chapter 7 of ISL", selected_slugs=None, catalog=_CAT)
    assert r.book_slug == "islp"
    assert r.chapter_id == "ch07"
    assert r.book_confidence >= 0.6


@pytest.mark.asyncio
async def test_resolve_book_expands_sections(monkeypatch):
    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return _json.dumps({
            "book_slug": "islp", "book_confidence": 0.9,
            "book_candidates": ["islp"], "chapter_id": "ch07",
            "requested_subtopics": [],
        })
    monkeypatch.setattr(_scope, "_chat", fake_chat)
    r = await _scope.resolve_book(
        "chapter 7 sections 7.2 up to 7.4 of ISL", selected_slugs=None, catalog=_CAT)
    assert r.requested_subtopics == ["7.2", "7.3", "7.4"]


from src.services.chat.agents._scope import maybe_clarify


def test_maybe_clarify_no_fire_on_confident_multi_candidate():
    from src.services.chat.schemas import BookResolution
    res = BookResolution(book_slug="islp", book_confidence=0.9,
                         book_candidates=["islp", "islpr"], chapter_id="")
    assert maybe_clarify(res, _CAT) is None  # confident → proceed despite 2 candidates


def test_maybe_clarify_caps_candidates():
    from src.services.chat.schemas import BookResolution, CatalogBook
    big = [CatalogBook(slug=f"b{i}", name=f"Book {i}", authors_short="X",
                       field="f", chapters=["ch01"]) for i in range(20)]
    res = BookResolution(book_slug="", book_confidence=0.0, book_candidates=[])
    clar = maybe_clarify(res, big)
    assert clar is not None and len(clar["candidates"]) <= 6


@pytest.mark.asyncio
async def test_resolve_book_single_selection_failopen(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(_scope, "_chat", boom)  # accepts any kwargs
    r = await _scope.resolve_book("teach ch02", selected_slugs=["islp"], catalog=_CAT)
    assert r.book_slug == "islp"
    assert r.book_confidence == 1.0
