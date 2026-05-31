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
