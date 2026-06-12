# src/services/chat/tests/test_facilitate_story_runner.py
import json
import pytest
from src.services.chat.agents import facilitate_story as fs
from src.services.chat.schemas import Source


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


@pytest.mark.asyncio
async def test_clarify_short_circuits(monkeypatch):
    monkeypatch.setattr(fs, "_resolve_one_section", lambda req: (None, None,
        {"type": "clarify", "reason": "book_unknown", "message": "pick", "candidates": []}))
    events = [e async for e in fs.run_facilitate_story(_Req("teach nothing"))]
    assert any(e.get("type") == "clarify" for e in events)
    assert not any(e.get("type") == "structured_output" for e in events)
