"""Structured-output gate wired into chapter.py stages."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.agents import chapter as ch


def _resp(content="{}"):
    class _Msg:
        pass
    class _Choice:
        pass
    msg = _Msg(); msg.content = content
    choice = _Choice(); choice.message = msg
    class _Resp:
        pass
    r = _Resp(); r.choices = [choice]
    return r


@pytest.mark.asyncio
async def test_chat_object_model_injects_response_format_token():
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return _resp("{}")

    client = AsyncMock()
    client.chat.completions.create = _create
    from src.services.chat.schemas import ChapterStitchOut
    with patch.object(ch, "aclient_for", return_value=client):
        await ch._chat(
            [{"role": "system", "content": "BASE"},
             {"role": "user", "content": "u"}],
            model="deepseek-v4-pro", max_tokens=100, schema=ChapterStitchOut,
        )
    assert captured["response_format"] == {"type": "json_object"}
    assert "<response_format>" in captured["messages"][0]["content"]
    assert "BASE" in captured["messages"][0]["content"]


@pytest.mark.asyncio
async def test_chat_schema_model_native_and_untouched():
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return _resp("{}")

    client = AsyncMock()
    client.chat.completions.create = _create
    from src.services.chat.schemas import ChapterStitchOut
    with patch.object(ch, "aclient_for", return_value=client):
        await ch._chat(
            [{"role": "system", "content": "BASE"}],
            model="gpt-4o", max_tokens=100, schema=ChapterStitchOut,
        )
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["messages"][0]["content"] == "BASE"


@pytest.mark.asyncio
async def test_stages_pass_their_schema():
    """map_sections/stitch/ground/resolve_subtopics each pass a schema to _chat."""
    from src.services.chat.schemas import (
        ChapterGroundOut, ChapterMapBlock, ChapterResolveMatches, ChapterStitchOut,
        Source, ChapterBlock,
    )
    seen = []

    async def _spy(messages, *, model, max_tokens, temperature=0.0, schema=None):
        seen.append(schema)
        return ('{"body":"x","citations":[],"math_blocks":[],"intro":"i","outro":"o",'
                '"ok":true,"unsupported":[],"confidence":1.0,"matches":[]}')

    # Build a real Source — title is "Alpha" so "zzz" won't substring-match.
    src = Source(
        rank=1,
        book="test-book",
        chapter="ch01",
        section="1.1",
        title="Alpha",
        excerpt="some excerpt",
        score=0.9,
        chunkId="chunk-001",
        chunk="full chunk text",
    )
    blk = ChapterBlock(
        h2_path="Alpha",
        section_id="chunk-001",
        body="block body text",
    )

    # Ensure resolve gate is on
    with patch.dict(os.environ, {"CHAPTER_RESOLVE": "1"}):
        with patch.object(ch, "_chat", _spy):
            await ch.map_sections([src], mode="resume", model="gpt-4o")
            await ch.stitch([blk], model="gpt-4o")
            await ch.ground([blk], [src], model="gpt-4o")
            # "zzz" does NOT substring-match "Alpha" -> LLM path fires
            await ch.resolve_subtopics(["zzz"], [src], model="gpt-4o")

    assert ChapterMapBlock in seen
    assert ChapterStitchOut in seen
    assert ChapterGroundOut in seen
    assert ChapterResolveMatches in seen
