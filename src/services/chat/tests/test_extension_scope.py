import asyncio
import src.services.chat.agents.extension_agents.scope as SC


def test_structure_files_are_ordered():
    sections = [
        {"section_id": "7.1", "h2_path": "Intro", "text": "intro text"},
        {"section_id": "7.2", "h2_path": "Random Variables", "text": "rv text"},
    ]
    files = SC.build_structure_files(sections)
    names = list(files.keys())
    assert names[0].startswith("/structure/00_")
    assert names[1].startswith("/structure/01_")
    assert "intro text" in files[names[0]]
    assert "Random Variables" in files[names[1]]


def test_aresolve_returns_clarify_when_ambiguous(monkeypatch):
    from src.services.chat.schemas import BookResolution

    async def _fake_resolve(message, *, selected_slugs, catalog, model=None):
        return BookResolution(book_slug="", book_confidence=0.1,
                              book_candidates=["a", "b"], chapter_id="",
                              requested_subtopics=[])
    monkeypatch.setattr(SC, "resolve_book", _fake_resolve)
    monkeypatch.setattr(SC, "maybe_clarify", lambda res, catalog: {"type": "clarify", "options": ["a", "b"]})

    clar, resolved = asyncio.run(
        SC.aresolve_scope_or_clarify("extend something", catalog=[], selected_slugs=[]))
    assert clar == {"type": "clarify", "options": ["a", "b"]}
    assert resolved is None


def test_aresolve_returns_resolution_when_clear(monkeypatch):
    from src.services.chat.schemas import BookResolution

    async def _fake_resolve(message, *, selected_slugs, catalog, model=None):
        return BookResolution(book_slug="hansen-probability", book_confidence=0.9,
                              book_candidates=["hansen-probability"], chapter_id="ch07",
                              requested_subtopics=[])
    monkeypatch.setattr(SC, "resolve_book", _fake_resolve)
    monkeypatch.setattr(SC, "maybe_clarify", lambda res, catalog: None)

    clar, resolved = asyncio.run(
        SC.aresolve_scope_or_clarify("extend hansen ch7", catalog=[], selected_slugs=[]))
    assert clar is None
    assert resolved.book_slug == "hansen-probability"
