"""Tests for src.services.chat.store.

Uses monkeypatch to redirect the DB to a tmp_path location so that no
files are written to data/chat.db during the test run.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import src.services.chat.store as store_module


# ---------------------------------------------------------------------------
# Fixture: redirect DB to a temp file and reinitialise schema
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the store at a fresh temp DB for every test."""
    test_db = tmp_path / "test_chat.db"
    monkeypatch.setattr(store_module, "DB_PATH", test_db)
    # Reset thread-local connection so the new path is used.
    store_module._local.conn = None  # type: ignore[attr-defined]
    store_module.init_db()


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


def test_create_conversation_returns_digest() -> None:
    digest = store_module.create_conversation(title="Intro to Stats", model_id="gpt-4o")
    assert digest.id
    assert digest.title == "Intro to Stats"
    assert digest.mode == "tutor"
    assert digest.modelId == "gpt-4o"
    assert digest.bookFilter == "ALL"
    assert digest.createdAt == digest.updatedAt


def test_get_conversation_roundtrip() -> None:
    created = store_module.create_conversation(
        title="Regression", mode="math", model_id="gpt-4o", book_filter=["islp"]
    )
    fetched = store_module.get_conversation(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.title == "Regression"
    assert fetched.mode == "math"
    assert fetched.bookFilter == ["islp"]


def test_get_conversation_missing_returns_none() -> None:
    assert store_module.get_conversation("nonexistent_id") is None


def test_list_conversations_ordering() -> None:
    c1 = store_module.create_conversation(title="First", model_id="gpt-4o")
    c2 = store_module.create_conversation(title="Second", model_id="gpt-4o")
    # Touch c1 so its updated_at is newer.
    store_module.touch_conversation(c1.id)

    listing = store_module.list_conversations()
    assert len(listing) == 2
    assert listing[0].id == c1.id   # most recently updated first
    assert listing[1].id == c2.id


def test_delete_conversation_returns_true() -> None:
    c = store_module.create_conversation(title="Temp", model_id="gpt-4o")
    assert store_module.delete_conversation(c.id) is True
    assert store_module.get_conversation(c.id) is None


def test_delete_conversation_missing_returns_false() -> None:
    assert store_module.delete_conversation("does_not_exist") is False


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def test_append_and_get_messages() -> None:
    c = store_module.create_conversation(title="Chat", model_id="gpt-4o")

    uid = store_module.append_message(
        conversation_id=c.id,
        role="user",
        content="What is a p-value?",
    )
    aid = store_module.append_message(
        conversation_id=c.id,
        role="assistant",
        content={"text": "A p-value measures…"},
        sources=[{"rank": 1, "book": "islp"}],
        figures=[{"ref": "fig1.1"}],
        metadata={"model": "gpt-4o", "latencyMs": 420},
    )

    msgs = store_module.get_messages(c.id)
    assert len(msgs) == 2

    user_msg = msgs[0]
    assert user_msg["id"] == uid
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "What is a p-value?"
    assert user_msg["sources"] is None
    assert user_msg["figures"] is None
    assert user_msg["metadata"] is None

    asst_msg = msgs[1]
    assert asst_msg["id"] == aid
    assert asst_msg["role"] == "assistant"
    assert asst_msg["content"] == {"text": "A p-value measures…"}
    assert asst_msg["sources"] == [{"rank": 1, "book": "islp"}]
    assert asst_msg["figures"] == [{"ref": "fig1.1"}]
    assert asst_msg["metadata"]["latencyMs"] == 420


def test_delete_conversation_cascades_messages() -> None:
    c = store_module.create_conversation(title="Cascade", model_id="gpt-4o")
    store_module.append_message(conversation_id=c.id, role="user", content="hello")
    store_module.delete_conversation(c.id)
    # After cascade delete the messages table should have no rows for this conv.
    assert store_module.get_messages(c.id) == []


def test_append_message_bumps_updated_at() -> None:
    c = store_module.create_conversation(title="Timing", model_id="gpt-4o")
    original_updated = c.updatedAt

    store_module.append_message(
        conversation_id=c.id, role="user", content="hi"
    )
    refreshed = store_module.get_conversation(c.id)
    assert refreshed is not None
    assert refreshed.updatedAt >= original_updated


# ---------------------------------------------------------------------------
# Prefs
# ---------------------------------------------------------------------------


def test_prefs_set_and_get() -> None:
    store_module.set_pref("theme", "dark")
    assert store_module.get_pref("theme") == "dark"


def test_prefs_get_missing_returns_default() -> None:
    assert store_module.get_pref("nonexistent") is None
    assert store_module.get_pref("nonexistent", 42) == 42


def test_prefs_upsert() -> None:
    store_module.set_pref("theme", "light")
    store_module.set_pref("theme", "dark")
    assert store_module.get_pref("theme") == "dark"


def test_prefs_json_types() -> None:
    store_module.set_pref("books", ["islp", "esl"])
    store_module.set_pref("count", 7)
    store_module.set_pref("nested", {"a": 1, "b": [2, 3]})

    assert store_module.get_pref("books") == ["islp", "esl"]
    assert store_module.get_pref("count") == 7
    assert store_module.get_pref("nested") == {"a": 1, "b": [2, 3]}
