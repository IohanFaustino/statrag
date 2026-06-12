"""Tests for control-character sanitization at the SSE seam.

TDD: written before the helper + wiring exist so the import fails (red).
After api.py is patched the tests go green.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import types
import pytest


# ---------------------------------------------------------------------------
# Import helper under test
# ---------------------------------------------------------------------------


def _import_strip_ctrl():
    """Import _strip_ctrl from api.py, reloading to pick up any edits."""
    # Remove cached module so we always get the latest version during dev.
    mod_name = "src.services.chat.api"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    return mod._strip_ctrl  # noqa: SLF001


# ---------------------------------------------------------------------------
# Unit tests for _strip_ctrl
# ---------------------------------------------------------------------------


class TestStripCtrl:
    def setup_method(self):
        self.strip = _import_strip_ctrl()

    def test_del_and_trailing_garbage_in_math(self):
        """DEL (0x7F) after $ is stripped; surrounding text kept."""
        result = self.strip("$\x7f\\hat\\theta$ and bia\x7f\x7fs")
        assert result == "$\\hat\\theta$ and bias"

    def test_nested_dict_strips_values_keeps_newline_tab(self):
        """NUL in value stripped; \\n and \\t preserved."""
        inp = {"aspects": {"tldr": "a\x00b", "keep": "line1\nline2\ttab"}}
        expected = {"aspects": {"tldr": "ab", "keep": "line1\nline2\ttab"}}
        assert self.strip(inp) == expected

    def test_list_with_mixed_types(self):
        """List entries (str + dict) each sanitized; C1 0x9F stripped."""
        inp = ["x\x01y", {"k": "z\x9fw"}]
        expected = ["xy", {"k": "zw"}]
        assert self.strip(inp) == expected

    def test_non_printable_range_c0(self):
        """All C0 chars except \\t, \\n, \\r are stripped."""
        # Build string with 0x00-0x1f; keep \\t=0x09, \\n=0x0a, \\r=0x0d
        all_c0 = "".join(chr(i) for i in range(0x20))
        result = self.strip(all_c0)
        assert result == "\t\n\r"

    def test_c1_range_stripped(self):
        """C1 range 0x7F-0x9F stripped."""
        inp = "".join(chr(i) for i in range(0x7F, 0xA0))
        result = self.strip(inp)
        assert result == ""

    def test_passthrough_non_string(self):
        """Numbers and None pass through unchanged."""
        strip = self.strip
        assert strip(42) == 42
        assert strip(3.14) == 3.14
        assert strip(None) is None
        assert strip(True) is True

    def test_keeps_printable_ascii_and_unicode(self):
        """Printable ASCII and unicode not touched."""
        s = "Hello, world! β α → ∞"
        assert self.strip(s) == s

    def test_qa_null_delta(self):
        """Reproduces the qa '$\\x00\\delta$' evidence case."""
        result = self.strip("$\x00\\delta$")
        assert result == "$\\delta$"

    def test_extension_prose_garbage(self):
        """Reproduces extension 'a $\\x01\\x0e\\x02\\x03... guarantee' evidence."""
        inp = "a $\x01\x0e\x02\x03 guarantee"
        result = self.strip(inp)
        assert result == "a $ guarantee"

    def test_carriage_return_kept(self):
        """\\r is explicitly kept."""
        assert self.strip("line1\r\nline2") == "line1\r\nline2"


# ---------------------------------------------------------------------------
# Seam test: chat_event_gen strips control chars before yielding + persisting
# ---------------------------------------------------------------------------


class TestChatEventGenSeam:
    """Drive chat_event_gen with a stubbed stream_chat that yields a
    structured_output event containing DEL inside math.  Assert the event
    yielded to the client is clean, AND that the persistence buffer received
    the clean dict.
    """

    @staticmethod
    def _make_dirty_event() -> dict:
        return {
            "type": "structured_output",
            "schema": "TutorAnswer",
            "data": {
                "aspects": {
                    "tldr": "$\x7f\\hat\\theta$",
                    "body": "clean prose\x00",
                }
            },
        }

    def test_seam_strips_before_yield_and_persist(self, monkeypatch):
        """Stub stream_chat; verify yielded event + persisted content are clean."""
        import src.services.chat.api as api_mod  # noqa: PLC0415

        dirty_event = self._make_dirty_event()

        async def _fake_stream_chat(req, *, history):
            yield dirty_event

        # Stub store so we can capture the persisted content
        persisted: list[dict] = []
        original_append = api_mod.store.append_message

        def _fake_append(**kwargs):
            persisted.append(kwargs)

        monkeypatch.setattr(api_mod, "stream_chat", _fake_stream_chat)
        monkeypatch.setattr(api_mod.store, "append_message", _fake_append)

        # Build a minimal ChatRequest
        from src.services.chat.schemas import ChatRequest  # noqa: PLC0415

        req = ChatRequest(
            message="test",
            mode="tutor",
            conversationId="test-conv-sanitize",
        )

        async def _run():
            events = []
            async for ev in api_mod.chat_event_gen(req):
                events.append(ev)
            return events

        events = asyncio.get_event_loop().run_until_complete(_run())

        # --- yielded event must be clean ---
        so_events = [e for e in events if e.get("type") == "structured_output"]
        assert so_events, "expected at least one structured_output event"
        data = so_events[0]["data"]
        assert "\x7f" not in data["aspects"]["tldr"], (
            "DEL still present in yielded event tldr"
        )
        assert data["aspects"]["tldr"] == "$\\hat\\theta$"
        assert "\x00" not in data["aspects"]["body"]

        # --- persisted content must be clean ---
        asst_calls = [c for c in persisted if c.get("role") == "assistant"]
        assert asst_calls, "expected assistant persist call"
        content = asst_calls[0]["content"]
        assert isinstance(content, dict)
        assert "\x7f" not in content["aspects"]["tldr"], (
            "DEL still present in persisted content"
        )
        assert content["aspects"]["tldr"] == "$\\hat\\theta$"
