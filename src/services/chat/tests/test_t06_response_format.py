"""T06 acceptance: native response_format constrained decoding (ADR-008)."""
from __future__ import annotations

import os

import pytest
from pydantic import BaseModel

from src.services.chat.llm.openai_client import OpenAIChat, _build_response_format


class _Toy(BaseModel):
    a: int
    b: str


# ---------------------------------------------------------------------------
# _build_response_format
# ---------------------------------------------------------------------------


def test_build_response_format_none_returns_none():
    assert _build_response_format(None) is None


def test_build_response_format_passes_dict_through():
    raw = {"type": "json_schema", "json_schema": {"name": "X", "schema": {}}}
    assert _build_response_format(raw) is raw


def test_build_response_format_from_pydantic_class():
    rf = _build_response_format(_Toy)
    assert rf is not None
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "_Toy"
    assert "properties" in rf["json_schema"]["schema"]


def test_build_response_format_unknown_object_returns_none():
    class _NoSchema:
        pass

    assert _build_response_format(_NoSchema()) is None


# ---------------------------------------------------------------------------
# Schema repair legacy env flag
# ---------------------------------------------------------------------------


def test_schema_repair_legacy_flag_present():
    """Env flag SCHEMA_REPAIR_LEGACY exists as the orchestrator escape hatch."""
    from src.services.chat import orchestrator

    # The orchestrator reads os.environ.get("SCHEMA_REPAIR_LEGACY") at request
    # time. We assert the variable is consulted by reading the source.
    import inspect

    src = inspect.getsource(orchestrator)
    assert "SCHEMA_REPAIR_LEGACY" in src
