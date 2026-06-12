# src/services/chat/tests/test_facilitate_story_runner.py
import json
import pytest
from src.services.chat.agents import facilitate_story as fs
from src.services.chat.agents.facilitate_story import _parse_draft
from src.services.chat.schemas import Source
from src.services.chat.schemas.output import FacilitateStoryDraft


class _Req:
    def __init__(self, msg, books=None):
        self.message = msg
        self.bookFilter = books or ["hansen"]
        self.model = "nano"
        self.stageModels = None
        self.conversationId = None


def _source():
    return Source(chunkId="hansen:ch07:7.4", title="7.4 Law of Large Numbers",
                  chunk="Theorem. The sample mean converges: $$\\bar X_n \\to \\mu$$.",
                  excerpt="", book="hansen", book_name="Probability", authors_short="Hansen",
                  page_from=120, page_to=122, chapter="ch07", section="7.4",
                  rank=1, score=0.9)


@pytest.mark.asyncio
async def test_emits_single_facilitate_story(monkeypatch):
    monkeypatch.setattr(fs, "_resolve_one_section", lambda req: (
        fs.ChapterScope(book_slug="hansen", chapter_id="ch07", section_id="7.4"), _source(), None))

    async def fake_chat(messages, **kw):
        sys = messages[0]["content"]
        if "MAP" in sys or "key_points" in sys:
            return json.dumps({"key_points": ["averages stabilise"],
                               "concepts": [{"term": "law of large numbers", "kind": "theorem", "status": "explained"}]})
        if "VERIFY" in sys or "fixed" in sys:
            return json.dumps({"ok": True, "unsupported": [], "confidence": 0.9})
        return json.dumps({"hook": "why", "takeaway": "done", "math_blocks": [],
                           "movements": [{"prose": "The [[c1]] is central.", "formal": None}]})
    monkeypatch.setattr(fs, "_chat", fake_chat)

    events = [e async for e in fs.run_facilitate_story(_Req("teach 7.4"))]
    payloads = [e for e in events if e.get("type") == "structured_output"]
    assert len(payloads) == 1
    data = payloads[0]["data"]
    assert payloads[0]["schema"] == "FacilitateStory"
    assert data["scope"]["section_id"] == "7.4"
    assert len(data["movements"]) == 1
    assert data["concepts"][0]["id"] == "c1"
    assert any(e.get("type") == "done" for e in events)


def test_parse_draft_truncated_json_returns_empty():
    """Regression: truncated JSON must not raise — returns empty FacilitateStoryDraft."""
    truncated = '{"hook": "why", "movements": [{"prose": "the story is cut off her'
    result = _parse_draft(truncated)
    assert isinstance(result, FacilitateStoryDraft)
    assert result.hook == ""
    assert result.movements == []
    assert result.takeaway == ""


def test_parse_draft_valid_json_round_trips():
    """Full valid JSON with one formal + one prose movement parses correctly."""
    payload = json.dumps({
        "hook": "Here is why it matters.",
        "takeaway": "Now you know.",
        "math_blocks": ["$$E[X] = \\mu$$"],
        "movements": [
            {"formal": {"kind": "theorem", "statement": "E[X] = mu", "explanation": "central [[c1]]"}, "prose": ""},
            {"prose": "Building on this, the variance follows.", "formal": None},
        ],
    })
    result = _parse_draft(payload)
    assert isinstance(result, FacilitateStoryDraft)
    assert result.hook == "Here is why it matters."
    assert result.takeaway == "Now you know."
    assert result.math_blocks == ["$$E[X] = \\mu$$"]
    assert len(result.movements) == 2
    assert result.movements[0].formal is not None
    assert result.movements[0].formal.statement == "E[X] = mu"
    assert result.movements[1].prose == "Building on this, the variance follows."


@pytest.mark.asyncio
async def test_clarify_short_circuits(monkeypatch):
    monkeypatch.setattr(fs, "_resolve_one_section", lambda req: (None, None,
        {"type": "clarify", "reason": "book_unknown", "message": "pick", "candidates": []}))
    events = [e async for e in fs.run_facilitate_story(_Req("teach nothing"))]
    assert any(e.get("type") == "clarify" for e in events)
    assert not any(e.get("type") == "structured_output" for e in events)


@pytest.mark.asyncio
async def test_empty_sections_yields_actionable_clarify_not_empty_section_list(monkeypatch):
    """When book/chapter resolves but fetch_chapter_sections returns [],
    the runner must NOT emit an empty section_clarify (reason='section_ambiguous',
    candidates=[]). Instead it must emit a helpful clarify."""
    from src.services.chat.schemas import BookResolution

    # Force inline path
    monkeypatch.setattr(fs, "_resolve_one_section",
                        lambda req: (_ for _ in ()).throw(NotImplementedError()))
    monkeypatch.setattr(fs, "parse_catalog", lambda: [])

    async def fake_resolve(*a, **k):
        return BookResolution(
            book_slug="hansen",
            book_confidence=0.95,
            book_candidates=["hansen"],
            chapter_id="ch99",
            requested_subtopics=[],
        )

    monkeypatch.setattr(fs, "resolve_book", fake_resolve)
    # maybe_clarify returns None → runner must hit the chapter_empty fallback
    monkeypatch.setattr(fs, "maybe_clarify", lambda res, cat: None)
    monkeypatch.setattr(fs, "fetch_chapter_sections", lambda *a, **k: [])

    class _Req:
        message = "teach me something"
        bookFilter = ["hansen"]
        model = "nano"
        stageModels = None
        conversationId = None

    events = [e async for e in fs.run_facilitate_story(_Req())]
    clars = [e for e in events if e.get("type") == "clarify"]
    assert clars, "expected a clarify event"
    # Must NOT be the empty section_ambiguous clarify
    assert clars[0]["reason"] != "section_ambiguous", (
        "got an empty section_ambiguous clarify — should be chapter_empty or a book/chapter clarify"
    )
    assert clars[0]["reason"] == "chapter_empty"
    assert not any(e.get("type") == "structured_output" for e in events)
