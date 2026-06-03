"""Structured-output gate wired into qa.py stages."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.agents import qa


def _resp(content="{}"):
    class _Msg: ...
    class _Choice: ...
    class _Resp: ...
    msg = _Msg(); msg.content = content
    choice = _Choice(); choice.message = msg
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
    from src.services.chat.schemas import QAVerifyOut
    with patch.object(qa, "aclient_for", return_value=client):
        await qa._chat(
            [{"role": "system", "content": "BASE"},
             {"role": "user", "content": "u"}],
            model="deepseek-v4-pro", max_tokens=100, schema=QAVerifyOut,
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
    from src.services.chat.schemas import QAVerifyOut
    with patch.object(qa, "aclient_for", return_value=client):
        await qa._chat(
            [{"role": "system", "content": "BASE"}],
            model="gpt-4o", max_tokens=100, schema=QAVerifyOut,
        )
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["messages"][0]["content"] == "BASE"


@pytest.mark.asyncio
async def test_stages_pass_their_schema():
    """extract_scope / generate_scoped / verify_grounding each hand _chat a schema."""
    from src.services.chat.schemas import (
        QAScope, QAGenerateOut, QAVerifyOut, Source,
    )
    seen = []

    async def _spy(messages, *, model, max_tokens, temperature=0.0, schema=None):
        seen.append(schema)
        return ('{"target_gap":"g","assumed_known":[],"answer_form":"explanation",'
                '"text":"t","citations":[],"math_blocks":[],'
                '"ok":true,"unsupported":[],"confidence":1.0}')

    src = Source(
        rank=1, book="b", chapter="ch01", section="1.1", title="Alpha",
        excerpt="ex", score=0.9, chunkId="c1", chunk="full chunk",
    )
    scope = QAScope(target_gap="g")

    with patch.object(qa, "_chat", _spy):
        await qa.extract_scope("question?", model="gpt-4o")
        await qa.generate_scoped(scope, [src], model="gpt-4o")
        await qa.verify_grounding(
            qa.QAAnswer(text="t", scope=scope), [src], model="gpt-4o"
        )

    assert QAScope in seen
    assert QAGenerateOut in seen
    assert QAVerifyOut in seen
