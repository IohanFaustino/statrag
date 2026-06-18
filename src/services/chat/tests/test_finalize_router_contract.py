"""Contract test: _stream_draft_via_router must log a warning when the parsed
JSON payload contains zero aspect keys (the empty-aspect-keys branch).

Regression: before Fix 2 this branch returned silently, making it impossible
to diagnose why deepseek/gemini produced ``(None, {})`` on the tolerant route.
"""
from __future__ import annotations

import json
import logging
import pytest

from src.services.chat.prompts.deep_tutor import ASPECT_HEADINGS


@pytest.fixture()
def _patch_get_llm(monkeypatch):
    """Patch get_llm so client.stream yields a JSON object with WRONG keys."""
    from src.services.chat.agents import deep_tutor as dt

    bad_payload = json.dumps({
        "question": "What is stationarity?",
        "answer_model": "test",
        "answer_json": {"body": "some answer"},
    })

    async def _fake_stream(self, messages, *, model, temperature, max_tokens, response_format=None):
        yield bad_payload

    class FakeClient:
        async def stream(self, messages, *, model, temperature, max_tokens, response_format=None):
            # Yield the bad payload in one chunk so buf accumulates it
            for chunk in [bad_payload]:
                yield chunk

    def fake_get_llm(model_name):
        return FakeClient(), model_name

    monkeypatch.setattr(dt, "get_llm", fake_get_llm)
    # Patch _cap_max_tokens to avoid unknown model issues
    monkeypatch.setattr(dt, "_cap_max_tokens", lambda m: 4096)


@pytest.mark.asyncio
async def test_router_warns_on_empty_aspect_keys(_patch_get_llm, caplog):
    """When _stream_draft_via_router parses JSON with no aspect keys,
    it must emit a warning containing 'no aspect keys found'."""
    from src.services.chat.agents.deep_tutor import _stream_draft_via_router

    accumulated = {k: "" for k in ASPECT_HEADINGS}
    with caplog.at_level(logging.WARNING):
        result, returned_acc = await _stream_draft_via_router(
            model="gemini-2.5-pro",
            messages=[{"role": "user", "content": "test"}],
            accumulated=accumulated,
            on_aspect_delta=None,
        )

    assert result is None, "Expected None when payload has zero aspect keys"
    assert "no aspect keys found" in caplog.text, (
        f"Expected 'no aspect keys found' in log output, got: {caplog.text!r}"
    )