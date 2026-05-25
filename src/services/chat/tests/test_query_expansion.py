"""Tests for src.services.chat.query_expansion.

All LLM calls are mocked — no real API calls are made.
"""
from __future__ import annotations

import os
import sys

import pytest
from unittest.mock import AsyncMock, patch

# ---------------------------------------------------------------------------
# Bootstrap: project root on PYTHONPATH, dummy API key
# ---------------------------------------------------------------------------

_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")


# ---------------------------------------------------------------------------
# Tests — hyde
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hyde_returns_text() -> None:
    """hyde should return the stripped LLM output."""
    from src.services.chat.query_expansion import hyde

    with patch(
        "src.services.chat.query_expansion._llm_short",
        new=AsyncMock(
            return_value=(
                "Ridge regression adds an L2 penalty to OLS, shrinking coefficients "
                "toward zero. The penalty parameter lambda balances bias and variance. "
                "As lambda increases, variance decreases but bias grows."
            )
        ),
    ):
        out = await hyde("what is ridge?")
        assert "ridge" in out.lower()


@pytest.mark.asyncio
async def test_hyde_strips_whitespace() -> None:
    """hyde should strip leading/trailing whitespace from the LLM output."""
    from src.services.chat.query_expansion import hyde

    with patch(
        "src.services.chat.query_expansion._llm_short",
        new=AsyncMock(return_value="  Some textbook excerpt.  "),
    ):
        out = await hyde("any query")
        assert out == "Some textbook excerpt."


# ---------------------------------------------------------------------------
# Tests — multi_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_query_parses_json_array() -> None:
    """multi_query should parse a JSON array and return up to n strings."""
    from src.services.chat.query_expansion import multi_query

    with patch(
        "src.services.chat.query_expansion._llm_short",
        new=AsyncMock(return_value='["alt phrasing 1", "alt phrasing 2", "alt phrasing 3"]'),
    ):
        out = await multi_query("ridge", n=3)
        assert len(out) == 3
        assert out[0] == "alt phrasing 1"


@pytest.mark.asyncio
async def test_multi_query_zero_returns_empty() -> None:
    """multi_query with n=0 must return [] without calling the LLM."""
    from src.services.chat.query_expansion import multi_query

    with patch(
        "src.services.chat.query_expansion._llm_short",
        new=AsyncMock(side_effect=AssertionError("should not be called")),
    ):
        out = await multi_query("ridge", n=0)
        assert out == []


@pytest.mark.asyncio
async def test_multi_query_malformed_json_returns_empty() -> None:
    """multi_query must return [] gracefully when the LLM returns invalid JSON."""
    from src.services.chat.query_expansion import multi_query

    with patch(
        "src.services.chat.query_expansion._llm_short",
        new=AsyncMock(return_value="not json at all"),
    ):
        out = await multi_query("ridge", n=3)
        assert out == []


@pytest.mark.asyncio
async def test_multi_query_truncates_to_n() -> None:
    """multi_query must not return more than n items even if LLM returns more."""
    from src.services.chat.query_expansion import multi_query

    with patch(
        "src.services.chat.query_expansion._llm_short",
        new=AsyncMock(return_value='["a", "b", "c", "d", "e"]'),
    ):
        out = await multi_query("ridge", n=2)
        assert len(out) == 2


# ---------------------------------------------------------------------------
# Tests — decompose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decompose_parses_array() -> None:
    """decompose should parse a JSON array of sub-questions."""
    from src.services.chat.query_expansion import decompose

    with patch(
        "src.services.chat.query_expansion._llm_short",
        new=AsyncMock(return_value='["sub1", "sub2"]'),
    ):
        out = await decompose("complex Q")
        assert out == ["sub1", "sub2"]


@pytest.mark.asyncio
async def test_decompose_malformed_json_returns_empty() -> None:
    """decompose must return [] gracefully on JSON-parse failure."""
    from src.services.chat.query_expansion import decompose

    with patch(
        "src.services.chat.query_expansion._llm_short",
        new=AsyncMock(return_value="this is not json"),
    ):
        out = await decompose("complex Q")
        assert out == []


# ---------------------------------------------------------------------------
# Tests — expand_queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expand_queries_dedup() -> None:
    """expand_queries must dedup case-insensitively while preserving order."""
    from src.services.chat.modes import RetrievalFlags
    from src.services.chat.query_expansion import expand_queries

    # multi_query returns the original string and its upper-case twin → dedup
    with patch(
        "src.services.chat.query_expansion.multi_query",
        new=AsyncMock(return_value=["ridge", "RIDGE", "L2 penalty"]),
    ):
        flags = RetrievalFlags(multi_query=3)
        out = await expand_queries("ridge", flags=flags)
        # Expected: ["ridge", "L2 penalty"] — "RIDGE" deduped against "ridge"
        assert len(out) == 2
        assert out[0] == "ridge"
        assert out[1] == "L2 penalty"


@pytest.mark.asyncio
async def test_expand_queries_no_flags() -> None:
    """With all flags off, expand_queries must return only the original query."""
    from src.services.chat.modes import RetrievalFlags
    from src.services.chat.query_expansion import expand_queries

    flags = RetrievalFlags()
    out = await expand_queries("ridge", flags=flags)
    assert out == ["ridge"]


@pytest.mark.asyncio
async def test_expand_queries_hyde_prepended() -> None:
    """HyDE expansion should appear immediately after the original query."""
    from src.services.chat.modes import RetrievalFlags
    from src.services.chat.query_expansion import expand_queries

    with patch(
        "src.services.chat.query_expansion.hyde",
        new=AsyncMock(return_value="Hypothetical textbook passage about ridge."),
    ):
        flags = RetrievalFlags(hyde=True)
        out = await expand_queries("ridge", flags=flags)
        assert out[0] == "ridge"
        assert out[1] == "Hypothetical textbook passage about ridge."


@pytest.mark.asyncio
async def test_expand_queries_decompose_appended() -> None:
    """Decomposed sub-questions should appear at the end of the query list."""
    from src.services.chat.modes import RetrievalFlags
    from src.services.chat.query_expansion import expand_queries

    with patch(
        "src.services.chat.query_expansion.decompose",
        new=AsyncMock(return_value=["What is ridge?", "How does L2 penalty work?"]),
    ):
        flags = RetrievalFlags(decompose=True)
        out = await expand_queries("ridge regression", flags=flags)
        assert out[0] == "ridge regression"
        assert "What is ridge?" in out
        assert "How does L2 penalty work?" in out


@pytest.mark.asyncio
async def test_expand_queries_hyde_failure_is_silent() -> None:
    """If hyde raises an exception, expand_queries must still return [original]."""
    from src.services.chat.modes import RetrievalFlags
    from src.services.chat.query_expansion import expand_queries

    with patch(
        "src.services.chat.query_expansion.hyde",
        new=AsyncMock(side_effect=RuntimeError("API error")),
    ):
        flags = RetrievalFlags(hyde=True)
        out = await expand_queries("ridge", flags=flags)
        assert out == ["ridge"]


@pytest.mark.asyncio
async def test_expand_queries_empty_hyde_result_excluded() -> None:
    """An empty string returned by hyde must not be added to the query list."""
    from src.services.chat.modes import RetrievalFlags
    from src.services.chat.query_expansion import expand_queries

    with patch(
        "src.services.chat.query_expansion.hyde",
        new=AsyncMock(return_value=""),
    ):
        flags = RetrievalFlags(hyde=True)
        out = await expand_queries("ridge", flags=flags)
        assert out == ["ridge"]
