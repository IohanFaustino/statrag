# src/services/chat/tests/test_extension_nodes.py
"""Extension v2 LLM nodes — structured outputs, parse-retry, mockable LLM."""
import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.agents.extension_agents.nodes import (
    SubjectList, TakeDraft, TakeDraftList, WriterOut, WriterBullet,
    run_storyteller, run_editor, run_miner, run_writer, run_judge, JudgeOut,
)


@pytest.mark.asyncio
async def test_storyteller_returns_takedraft():
    draft = TakeDraft(idx=0, heading="Chebyshev", story="The chapter opens…",
                      key_items=["tail bound", "finite variance"])
    fake = AsyncMock(return_value=draft)
    with patch("src.services.chat.agents.extension_agents.nodes._ainvoke", fake):
        out = await run_storyteller(idx=0, section={"h2_path": "7.4 Chebyshev", "text": "…"},
                                    prev_heading=None, stage_models=None)
    assert out.idx == 0 and out.heading == "Chebyshev"


@pytest.mark.asyncio
async def test_storyteller_parse_failure_degrades_to_flagged_raw_take():
    fake = AsyncMock(side_effect=ValueError("parse"))
    with patch("src.services.chat.agents.extension_agents.nodes._ainvoke", fake):
        out = await run_storyteller(idx=2, section={"h2_path": "7.6 X", "text": "Raw section body."},
                                    prev_heading="prev", stage_models=None)
    assert out.idx == 2 and "7.6 X" in out.heading
    assert out.degraded is True and "Raw section body." in out.story
    assert fake.await_count == 2          # one attempt + one repair retry


@pytest.mark.asyncio
async def test_writer_output_carries_evidence_ids():
    wo = WriterOut(bullets=[WriterBullet(subject="Why δ⁻²", body="Because…",
                                         evidence_ids=["e1"])])
    fake = AsyncMock(return_value=wo)
    with patch("src.services.chat.agents.extension_agents.nodes._ainvoke", fake):
        out = await run_writer(take_idx=0, take_heading="h", take_story="s",
                               subjects=[], evidence=[], stage_models=None)
    assert out[0].evidence_ids == ["e1"] and out[0].take_idx == 0


@pytest.mark.asyncio
async def test_judge_returns_failed_subjects():
    fake = AsyncMock(return_value=JudgeOut(failed_subjects=["history of LLN"]))
    with patch("src.services.chat.agents.extension_agents.nodes._ainvoke", fake):
        failed = await run_judge(take_heading="h", subjects=["a", "history of LLN"],
                                 bullets_summary="…", stage_models=None)
    assert failed == ["history of LLN"]


@pytest.mark.asyncio
async def test_run_editor_exception_returns_original_drafts_and_logs(caplog):
    drafts = [
        TakeDraft(idx=0, heading="Take A", story="Story A"),
        TakeDraft(idx=1, heading="Take B", story="Story B"),
    ]
    fake = AsyncMock(side_effect=RuntimeError("network error"))
    with caplog.at_level(logging.WARNING,
                         logger="src.services.chat.agents.extension_agents.nodes"):
        with patch("src.services.chat.agents.extension_agents.nodes._ainvoke", fake):
            result = await run_editor(drafts, stage_models=None)
    assert result == sorted(drafts, key=lambda d: d.idx)
    assert any("story_editor bypassed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_run_miner_exception_returns_empty_list():
    take = TakeDraft(idx=0, heading="Take A", story="Story A")
    fake = AsyncMock(side_effect=RuntimeError("network error"))
    with patch("src.services.chat.agents.extension_agents.nodes._ainvoke", fake):
        result = await run_miner(take=take, stage_models=None)
    assert result == []
