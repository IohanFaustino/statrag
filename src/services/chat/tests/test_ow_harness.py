"""Tests for the orchestrator-workers harness scaffold + eval helpers."""
import asyncio
from unittest.mock import patch
from src.services.chat.agents import orchestrator_workers as OW
from src.services.chat.schemas.output import AuthorBrief
from src.services.chat.schemas import Source


def _src(rank, author):
    return Source(rank=rank, book="b", chapter="c", section="s", title="t",
                  excerpt="", score=1.0, chunkId=f"x{rank}", chunk="text",
                  authors_short=author)


def test_on_briefs_hook_receives_briefs():
    captured = {}
    srcs = [_src(1, "Hansen"), _src(2, "Wooldridge")]

    async def fake_worker(query, thesis, author, s, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} summary",
                           key_points=[f"{author} kp"], source_ranks=[s[0].rank])

    async def fake_stream(*a, **k):
        from src.services.chat.schemas.output import DeepTutorAnswer
        return DeepTutorAnswer(
            tldr="t", definition="d", formal_statement="",
            example_intuition="e", applications="a", further_reading="f"
        ), {}

    with patch.object(OW, "run_author_worker", side_effect=fake_worker), \
         patch.object(OW, "_stream_structured", side_effect=fake_stream):
        OW.run_orchestrator_workers
        ans, _ = asyncio.run(OW.run_orchestrator_workers(
            "q", srcs, None, on_briefs=lambda b: captured.setdefault("briefs", b)))
    assert "briefs" in captured
    assert {b.author for b in captured["briefs"]} == {"Hansen", "Wooldridge"}
