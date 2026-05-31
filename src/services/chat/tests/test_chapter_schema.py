"""Validation tests for the chapter-mode output schemas."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.services.chat.schemas import (
    ChapterBlock,
    ChapterDigest,
    ChapterScope,
    ResolvedSubtopic,
)


def test_chapter_scope_defaults():
    scope = ChapterScope(book_slug="islp", chapter_id="ch02")
    assert scope.requested_subtopics == []
    assert scope.resolution == []


def test_resolved_subtopic_roundtrip():
    r = ResolvedSubtopic(asked="the tradeoff", matched_h2="2.2 | Bias-Variance",
                         section_id="2.2", score=0.81)
    assert r.matched_h2.endswith("Bias-Variance")


def test_chapter_digest_minimal_and_block_order_preserved():
    blocks = [
        ChapterBlock(h2_path="2.1 | A", section_id="2.1", body="first"),
        ChapterBlock(h2_path="2.2 | B", section_id="2.2", body="second"),
    ]
    d = ChapterDigest(
        mode="facilitate",
        scope=ChapterScope(book_slug="islp", chapter_id="ch02"),
        blocks=blocks,
    )
    assert [b.section_id for b in d.blocks] == ["2.1", "2.2"]
    assert d.intro == "" and d.outro == ""
    assert d.citations == [] and d.grounding == {}


def test_chapter_digest_rejects_bad_mode():
    with pytest.raises(ValidationError):
        ChapterDigest(
            mode="explain",  # not in Literal
            scope=ChapterScope(book_slug="islp", chapter_id="ch02"),
            blocks=[],
        )
