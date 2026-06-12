# src/services/chat/tests/test_facilitate_story_schema.py
import pytest
from pydantic import ValidationError
from src.services.chat.schemas.output import (
    FormalStatement, Movement, FacilitateStoryDraft, FacilitateStory, ChapterScope,
)


def test_movement_prose_only_ok():
    m = Movement(prose="The law of large numbers says averages stabilise.")
    assert m.prose and m.formal is None


def test_movement_formal_only_ok():
    fs = FormalStatement(kind="theorem", statement="$$\\bar X_n \\to \\mu$$",
                         explanation="elements ... intuition ... close.")
    m = Movement(formal=fs)
    assert m.formal and not m.prose


def test_movement_rejects_both_empty():
    with pytest.raises(ValidationError):
        Movement()


def test_movement_rejects_both_populated():
    fs = FormalStatement(kind="lemma", statement="x", explanation="y")
    with pytest.raises(ValidationError):
        Movement(prose="some prose", formal=fs)


def test_movement_rejects_whitespace_prose():
    with pytest.raises(ValidationError):
        Movement(prose="   ")


def test_formal_statement_rejects_empty_statement():
    with pytest.raises(ValidationError):
        FormalStatement(kind="theorem", statement="   ", explanation="x")


def test_formal_statement_allows_empty_explanation():
    fs = FormalStatement(kind="definition", statement="$$f(x) = x^2$$", explanation="")
    assert fs.statement and fs.explanation == ""


def test_draft_has_no_citation_or_provenance_field():
    fields = set(FacilitateStoryDraft.model_fields)
    assert "citations" not in fields and "concepts" not in fields and "provenance" not in fields
    assert fields == {"hook", "movements", "takeaway", "math_blocks"}


def test_facilitate_story_roundtrip_and_discriminator():
    story = FacilitateStory(
        mode="facilitate_story",
        scope=ChapterScope(book_slug="hansen", chapter_id="ch07", section_id="7.4"),
        hook="why it matters", movements=[Movement(prose="p")], takeaway="t")
    d = story.model_dump()
    assert d["mode"] == "facilitate_story"
    assert FacilitateStory(**d).scope.section_id == "7.4"


def test_chapter_scope_section_id_defaults_empty():
    assert ChapterScope(book_slug="b", chapter_id="ch01").section_id == ""
