"""Tests for the DeepSeek thinking-disable helper (draft-path config artifact fix).

DeepSeek v4 model ids (``deepseek-v4-pro``, ``deepseek-chat``) default to
THINKING mode, which spends the output budget on reasoning and returns empty
``content`` on the structured draft path. ``deepseek-reasoner`` is a genuine
chain-of-thought model where thinking is the point — it must keep thinking.
"""
from __future__ import annotations

from unittest.mock import patch

from src.services.chat.llm.deepseek_client import _thinking_extra_body

_DISABLED = {"thinking": {"type": "disabled"}}


def test_v4_pro_disables_thinking() -> None:
    """deepseek-v4-pro must request thinking disabled (avoids empty content)."""
    assert _thinking_extra_body("deepseek-v4-pro") == _DISABLED


def test_deepseek_chat_disables_thinking() -> None:
    """deepseek-chat must request thinking disabled."""
    assert _thinking_extra_body("deepseek-chat") == _DISABLED


def test_reasoner_keeps_thinking() -> None:
    """deepseek-reasoner is a CoT model — thinking must NOT be disabled."""
    assert _thinking_extra_body("deepseek-reasoner") is None


def test_env_flag_off_keeps_thinking() -> None:
    """Setting DEEPSEEK_DISABLE_THINKING=0 must leave thinking untouched."""
    with patch.dict("os.environ", {"DEEPSEEK_DISABLE_THINKING": "0"}):
        assert _thinking_extra_body("deepseek-v4-pro") is None
