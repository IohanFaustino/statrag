"""StoryDigest schema (extension v2)."""
import pytest
from pydantic import ValidationError

from src.services.chat.schemas.output import StoryCitation, CuriosityItem, StoryDigest, Take


def _corpus_citation(**over):
    base = dict(kind="corpus", label="Moss — Probability §6.5.2, pp. 142–144",
                book_slug="moss", book_name="Probability", authors="Moss", year=2020,
                chapter="ch06", section_id="6.5.2", pages="142–144", chunk_id="abc123")
    base.update(over)
    return StoryCitation(**base)


def test_corpus_citation_roundtrip():
    c = _corpus_citation()
    assert c.kind == "corpus" and c.url is None and c.chunk_id == "abc123"


def test_wikipedia_citation_minimal():
    c = StoryCitation(kind="wikipedia", label="Wikipedia: Chebyshev's inequality",
                      title="Chebyshev's inequality",
                      url="https://en.wikipedia.org/wiki/Chebyshev%27s_inequality")
    assert c.book_slug is None and c.url.startswith("https://")


def test_curiosity_item_requires_at_least_one_citation():
    with pytest.raises(ValidationError):
        CuriosityItem(subject="s", body="b", citations=[])


def test_story_digest_shape():
    item = CuriosityItem(subject="Why $\\delta^{-2}$", body="Because…",
                         citations=[_corpus_citation()])
    take = Take(heading="Chebyshev", story="The chapter opens…", items=[item])
    d = StoryDigest(book="hansen-probability", chapter="ch07 · 7.4–7.5",
                    takes=[take], unfilled_subjects=["history of LLN"])
    assert d.takes[0].items[0].citations[0].book_slug == "moss"
    assert StoryDigest(**d.model_dump()) == d  # persistence roundtrip


def test_take_items_default_empty():
    assert Take(heading="h", story="s").items == []
