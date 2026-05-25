"""Live integration test for Groq native JSON-object response_format.

Validates the "trust Groq native JSON mode" decision (no fallback coercion).
Skipped automatically when GROQ_API_KEY is unset so CI without secrets stays
green.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from src.services.chat.llm.base import ChatMessage
from src.services.chat.llm.groq_client import GroqChat

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="GROQ_API_KEY not set"),
]


@pytest.mark.parametrize(
    "model_id",
    [
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.3-70b-versatile",
        pytest.param(
            "openai/gpt-oss-20b",
            marks=pytest.mark.xfail(
                reason="gpt-oss reasoning models emit pre-JSON tokens; Groq json_object "
                "validator rejects. Use orchestrator repair loop or json_schema mode.",
                strict=False,
            ),
        ),
    ],
)
def test_groq_json_object_response_parses(model_id: str) -> None:
    """response_format=json_object must yield a parseable JSON object."""

    async def _run() -> str:
        client = GroqChat()
        chunks: list[str] = []
        async for delta in client.stream(
            [
                ChatMessage(role="system", content='Reply ONLY with JSON: {"ok": true, "n": 42}'),
                ChatMessage(role="user", content="Send the JSON now."),
            ],
            model=model_id,
            temperature=0.0,
            max_tokens=64,
            response_format={"type": "json_object"},
        ):
            chunks.append(delta)
        return "".join(chunks)

    out = asyncio.run(_run())
    parsed = json.loads(out)
    assert isinstance(parsed, dict)
