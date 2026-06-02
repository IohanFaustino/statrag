"""Tutor structured-output capability gate."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.services.chat.llm.structured import JsonMode
from src.services.chat.schemas.output import TutorAnswer


@pytest.mark.asyncio
async def test_schema_model_passes_response_format(monkeypatch):
    monkeypatch.delenv("TUTOR_FREE_TEXT", raising=False)
    from src.services.chat.mode_impls import tutor as t
    t.build_agent.cache_clear()
    captured = {}

    def _fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    async def _fake_ckpt():
        return None

    with patch.object(t, "create_agent", _fake_create_agent), \
         patch.object(t, "json_mode_for", return_value=JsonMode.SCHEMA), \
         patch.object(t, "get_async_checkpointer", _fake_ckpt):
        await t.build_agent()
    assert captured.get("response_format") is TutorAnswer
    assert captured["system_prompt"]


@pytest.mark.asyncio
async def test_object_model_drops_schema_and_appends_hint(monkeypatch):
    monkeypatch.delenv("TUTOR_FREE_TEXT", raising=False)
    from src.services.chat.mode_impls import tutor as t
    t.build_agent.cache_clear()
    captured = {}

    def _fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    async def _fake_ckpt():
        return None

    with patch.object(t, "create_agent", _fake_create_agent), \
         patch.object(t, "json_mode_for", return_value=JsonMode.OBJECT), \
         patch.object(t, "get_async_checkpointer", _fake_ckpt):
        await t.build_agent()
    assert "response_format" not in captured
    assert "json" in captured["system_prompt"].lower()
