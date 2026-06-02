"""Structured-output gate wired into _scope.resolve_book (PARSE stage)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.agents import _scope
from src.services.chat.schemas import CatalogBook


def _resp(content):
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


def _catalog():
    return [CatalogBook(slug="hansen", name="Probability", authors_short="Hansen",
                        field="stats", chapters=["ch01"])]


_PARSE_JSON = ('{"book_slug":"hansen","book_confidence":0.9,'
               '"book_candidates":["hansen"],"chapter_id":"ch01",'
               '"requested_subtopics":[]}')


@pytest.mark.asyncio
async def test_resolve_book_object_model_injects_token():
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return _resp(_PARSE_JSON)

    client = AsyncMock()
    client.chat.completions.create = _create
    with patch.object(_scope, "aclient_for", return_value=client):
        res = await _scope.resolve_book(
            "hansen ch1", selected_slugs=None, catalog=_catalog(),
            model="deepseek-v4-pro")
    assert res.book_slug == "hansen"
    assert captured["response_format"] == {"type": "json_object"}
    assert "<response_format>" in captured["messages"][0]["content"]


@pytest.mark.asyncio
async def test_resolve_book_schema_model_native():
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return _resp(_PARSE_JSON)

    client = AsyncMock()
    client.chat.completions.create = _create
    with patch.object(_scope, "aclient_for", return_value=client):
        await _scope.resolve_book(
            "hansen ch1", selected_slugs=None, catalog=_catalog(), model="gpt-4o")
    assert captured["response_format"]["type"] == "json_schema"
    assert "<response_format>" not in captured["messages"][0]["content"]
