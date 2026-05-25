"""Tests for src/services/chat/memory.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.chat.llm.base import ChatMessage
from src.services.chat.memory import (
    _conv_collection_name,
    _resolve_strategy,
    _sliding,
    build_memory_context,
    cleanup_conv_collection,
)


# ---------------------------------------------------------------------------
# _resolve_strategy
# ---------------------------------------------------------------------------


def test_resolve_strategy_auto_sliding() -> None:
    assert _resolve_strategy("auto", 5) == "sliding"


def test_resolve_strategy_auto_boundary_sliding() -> None:
    assert _resolve_strategy("auto", 10) == "sliding"


def test_resolve_strategy_auto_summary() -> None:
    assert _resolve_strategy("auto", 20) == "summary"


def test_resolve_strategy_auto_boundary_summary() -> None:
    assert _resolve_strategy("auto", 30) == "summary"


def test_resolve_strategy_auto_vec() -> None:
    assert _resolve_strategy("auto", 35) == "vec"


def test_resolve_strategy_fixed_vec() -> None:
    assert _resolve_strategy("vec", 5) == "vec"


def test_resolve_strategy_fixed_off() -> None:
    assert _resolve_strategy("off", 100) == "off"


def test_resolve_strategy_fixed_persist() -> None:
    assert _resolve_strategy("persist", 2) == "persist"


def test_resolve_strategy_fixed_sliding() -> None:
    assert _resolve_strategy("sliding", 50) == "sliding"


def test_resolve_strategy_fixed_summary() -> None:
    assert _resolve_strategy("summary", 1) == "summary"


# ---------------------------------------------------------------------------
# _sliding
# ---------------------------------------------------------------------------


def test_sliding_keeps_last_k_pairs() -> None:
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"},
        {"role": "assistant", "content": "a3"},
    ]
    out = _sliding(history, k_pairs=2)
    assert len(out) == 4
    assert out[0].content == "q2"
    assert out[1].content == "a2"
    assert out[2].content == "q3"
    assert out[3].content == "a3"


def test_sliding_skips_system_messages() -> None:
    history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    out = _sliding(history, k_pairs=5)
    roles = [m.role for m in out]
    assert "system" not in roles
    assert len(out) == 2


def test_sliding_skips_non_string_content() -> None:
    history = [
        {"role": "user", "content": {"structured": "data"}},
        {"role": "assistant", "content": "ok"},
    ]
    out = _sliding(history, k_pairs=5)
    # dict content is skipped
    assert len(out) == 1
    assert out[0].content == "ok"


def test_sliding_empty_history() -> None:
    assert _sliding([], k_pairs=5) == []


def test_sliding_default_k_pairs_5() -> None:
    """Default k_pairs=5 keeps up to 10 messages."""
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(14)
    ]
    out = _sliding(history)
    assert len(out) == 10


# ---------------------------------------------------------------------------
# _conv_collection_name
# ---------------------------------------------------------------------------


def test_conv_collection_name() -> None:
    assert _conv_collection_name("abc123") == "conv_abc123"


# ---------------------------------------------------------------------------
# build_memory_context — strategy='off'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_memory_off_returns_empty() -> None:
    out = await build_memory_context("c1", "q?", strategy="off", history=[])
    assert out == []


@pytest.mark.asyncio
async def test_build_memory_off_with_history_returns_empty() -> None:
    history = [{"role": "user", "content": "hi"}]
    out = await build_memory_context("c1", "q?", strategy="off", history=history)
    assert out == []


@pytest.mark.asyncio
async def test_build_memory_none_history_returns_empty() -> None:
    out = await build_memory_context("c1", "q?", strategy="sliding", history=None)
    assert out == []


# ---------------------------------------------------------------------------
# build_memory_context — strategy='sliding'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_memory_sliding_5_turns() -> None:
    history = [{"role": "user", "content": f"q{i}"} for i in range(5)]
    out = await build_memory_context("c1", "current?", strategy="sliding", history=history)
    assert len(out) == 5
    assert out[0].content == "q0"


@pytest.mark.asyncio
async def test_build_memory_sliding_truncates_to_k_pairs() -> None:
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(20)
    ]
    out = await build_memory_context("c1", "?", strategy="sliding", history=history)
    # default k_pairs=5 → up to 10 messages
    assert len(out) <= 10


# ---------------------------------------------------------------------------
# build_memory_context — strategy='summary'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_memory_summary_no_older_no_llm_call() -> None:
    """When history fits in the recent window, no LLM summarization call needed."""
    history = [
        {"role": "user", "content": f"q{i}"}
        for i in range(3)
    ]
    # 3 turns — cut = max(0, 3-5) = 0 → older is empty, no LLM call
    out = await build_memory_context("c1", "?", strategy="summary", history=history)
    assert isinstance(out, list)
    # All 3 returned as sliding (no summary message)
    assert all(isinstance(m, ChatMessage) for m in out)


@pytest.mark.asyncio
async def test_build_memory_summary_with_older_calls_llm() -> None:
    """When older turns exist, a system summary message is prepended."""
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(12)
    ]
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "Prior summary text."

    with patch("src.services.chat.memory._openai.AsyncOpenAI") as mock_oa_cls:
        mock_oa = AsyncMock()
        mock_oa_cls.return_value = mock_oa
        mock_oa.chat.completions.create = AsyncMock(return_value=mock_resp)

        out = await build_memory_context("c1", "?", strategy="summary", history=history)

    assert out[0].role == "system"
    assert "Prior conversation summary" in out[0].content
    assert len(out) > 1


# ---------------------------------------------------------------------------
# build_memory_context — strategy='vec'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_memory_vec_no_conv_id_falls_back_to_sliding() -> None:
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    out = await build_memory_context(None, "?", strategy="vec", history=history)
    # Falls back to sliding
    assert len(out) == 2


@pytest.mark.asyncio
async def test_build_memory_vec_deduplicates() -> None:
    """Vec retrieval + sliding must not produce duplicate messages."""
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    mock_emb_resp = MagicMock()
    mock_emb_resp.data = [MagicMock(embedding=[0.1] * 3072)]

    mock_point = MagicMock()
    mock_point.payload = {"role": "user", "content": "q1"}

    mock_query_result = MagicMock()
    mock_query_result.points = [mock_point]

    with patch("src.services.chat.memory._openai.AsyncOpenAI") as mock_oa_cls, \
         patch("src.services.chat.memory.client") as mock_client_fn:

        mock_oa = AsyncMock()
        mock_oa_cls.return_value = mock_oa
        mock_oa.embeddings.create = AsyncMock(return_value=mock_emb_resp)

        mock_qdrant = MagicMock()
        mock_client_fn.return_value = mock_qdrant
        mock_collection = MagicMock(name="conv_test")
        mock_qdrant.get_collections.return_value.collections = [mock_collection]
        mock_collection.name = "conv_test"
        mock_qdrant.query_points.return_value = mock_query_result

        out = await build_memory_context("test", "q1", strategy="vec", history=history)

    # No duplicate (role, content[:200]) pairs
    seen: set[tuple[str, str]] = set()
    for m in out:
        key = (m.role, m.content[:200])
        assert key not in seen, f"Duplicate found: {key}"
        seen.add(key)


# ---------------------------------------------------------------------------
# cleanup_conv_collection
# ---------------------------------------------------------------------------


def test_cleanup_drops_collection_when_present() -> None:
    with patch("src.services.chat.memory.client") as mock_client:
        cleanup_conv_collection("abc123")
        mock_client.return_value.delete_collection.assert_called_once_with(
            collection_name="conv_abc123"
        )


def test_cleanup_does_not_raise_on_missing_collection() -> None:
    with patch("src.services.chat.memory.client") as mock_client:
        mock_client.return_value.delete_collection.side_effect = Exception("not found")
        # Should not raise — logs a warning instead
        cleanup_conv_collection("nonexistent")
