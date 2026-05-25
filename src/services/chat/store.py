"""SQLite-backed conversation store for the chat service.

Thread-safe, sync API. FastAPI callers use ``run_in_threadpool`` or a
regular threadpool executor — no async needed here.

Chinese wall: imports only ``src.core.config``, stdlib, fastapi, and
local schemas. Never imports from ingestion or other services.

The DB is NOT created at import time. ``init_db()`` must be called
explicitly by application startup code (or by tests after monkeypatching
``DB_PATH``). All public functions call ``_ensure_init()`` lazily so that
a plain import does not touch the filesystem.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from src.core.config import DATA_DIR
from src.services.chat.memory import cleanup_conv_collection
from src.services.chat.schemas import ConversationDigest

# ---------------------------------------------------------------------------
# DB path — module-level so tests can monkeypatch it before calling init_db()
# ---------------------------------------------------------------------------

DB_PATH: Path = DATA_DIR / "chat.db"

# ---------------------------------------------------------------------------
# Thread-local connection + initialisation flag
# ---------------------------------------------------------------------------

_local = threading.local()
_db_initialised: bool = False

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'tutor',
    model_id     TEXT NOT NULL,
    book_filter  TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    sources          TEXT,
    figures          TEXT,
    metadata         TEXT,
    timestamp        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prefs (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS study_plans (
    conv_id    TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv
    ON messages(conversation_id, timestamp);
"""


# ---------------------------------------------------------------------------
# Public: init
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create tables and enable WAL mode.

    Must be called before any data access. Safe to call multiple times
    (idempotent). Tests call this *after* monkeypatching ``DB_PATH``.
    """
    global _db_initialised
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Drop any stale per-thread connection so the (possibly patched) path is used.
    _local.conn = None
    conn = _get_conn()
    conn.executescript(_DDL)
    conn.commit()
    _db_initialised = True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_conn() -> sqlite3.Connection:
    """Return a per-thread SQLite connection, opening it on first use."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def _ensure_init() -> None:
    """Auto-init the DB on first use if ``init_db()`` was not called yet."""
    if not _db_initialised:
        init_db()


@contextmanager
def _cursor() -> Generator[sqlite3.Cursor, None, None]:
    _ensure_init()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _row_to_digest(row: sqlite3.Row) -> ConversationDigest:
    book_filter: list[str] | str = json.loads(row["book_filter"])
    return ConversationDigest(
        id=row["id"],
        title=row["title"],
        mode=row["mode"],
        modelId=row["model_id"],
        bookFilter=book_filter,
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Public: conversations
# ---------------------------------------------------------------------------


def create_conversation(
    *,
    title: str,
    mode: str = "tutor",
    model_id: str,
    book_filter: list[str] | str = "ALL",
) -> ConversationDigest:
    """Insert a new conversation row and return its digest."""
    cid = _new_id()
    now = _now()
    bf_json = json.dumps(book_filter)
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations
                (id, title, mode, model_id, book_filter, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cid, title, mode, model_id, bf_json, now, now),
        )
    return ConversationDigest(
        id=cid,
        title=title,
        mode=mode,  # type: ignore[arg-type]
        modelId=model_id,
        bookFilter=book_filter,  # type: ignore[arg-type]
        createdAt=now,
        updatedAt=now,
    )


def get_conversation(conv_id: str) -> ConversationDigest | None:
    """Return a single conversation digest, or None if not found."""
    with _cursor() as cur:
        cur.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
        row = cur.fetchone()
    return _row_to_digest(row) if row else None


def list_conversations() -> list[ConversationDigest]:
    """Return all conversations ordered by updated_at descending."""
    with _cursor() as cur:
        cur.execute("SELECT * FROM conversations ORDER BY updated_at DESC")
        rows = cur.fetchall()
    return [_row_to_digest(r) for r in rows]


def delete_conversation(conv_id: str) -> bool:
    """Delete conversation and cascade-delete its messages. Return True if found."""
    with _cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        deleted = cur.rowcount > 0
    return deleted


def touch_conversation(conv_id: str) -> None:
    """Bump updated_at to now for the given conversation."""
    with _cursor() as cur:
        cur.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now(), conv_id),
        )


# ---------------------------------------------------------------------------
# Public: messages
# ---------------------------------------------------------------------------


def append_message(
    *,
    conversation_id: str,
    role: str,
    content: dict | list | str,
    sources: list | None = None,
    figures: list | None = None,
    metadata: dict | None = None,
) -> str:
    """Insert a message row and bump the parent conversation's updated_at.

    Returns the new message id.
    """
    mid = _new_id()
    now = _now()
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, sources, figures, metadata, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mid,
                conversation_id,
                role,
                json.dumps(content),
                json.dumps(sources) if sources is not None else None,
                json.dumps(figures) if figures is not None else None,
                json.dumps(metadata) if metadata is not None else None,
                now,
            ),
        )
    touch_conversation(conversation_id)
    return mid


def get_messages(conv_id: str) -> list[dict]:
    """Return all messages for a conversation with JSON columns decoded."""
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp",
            (conv_id,),
        )
        rows = cur.fetchall()

    result: list[dict[str, Any]] = []
    for r in rows:
        result.append(
            {
                "id": r["id"],
                "conversation_id": r["conversation_id"],
                "role": r["role"],
                "content": json.loads(r["content"]),
                "timestamp": r["timestamp"],
                "sources": json.loads(r["sources"]) if r["sources"] else None,
                "figures": json.loads(r["figures"]) if r["figures"] else None,
                "metadata": json.loads(r["metadata"]) if r["metadata"] else None,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Public: prefs
# ---------------------------------------------------------------------------


def set_pref(key: str, value: Any) -> None:
    """Upsert a preference value (stored as JSON)."""
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO prefs (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def get_pref(key: str, default: Any = None) -> Any:
    """Retrieve a preference value, returning ``default`` if absent."""
    with _cursor() as cur:
        cur.execute("SELECT value FROM prefs WHERE key = ?", (key,))
        row = cur.fetchone()
    return json.loads(row["value"]) if row else default


# ---------------------------------------------------------------------------
# Public: study_plans
# ---------------------------------------------------------------------------


def upsert_study_plan(conv_id: str, plan_json: dict, *, version: int) -> None:
    """Insert or replace a study plan for the given conversation.

    Args:
        conv_id: Conversation identifier (primary key).
        plan_json: The :class:`~src.services.chat.schemas.output.StudyPlan`
            dict to persist (serialised to JSON).
        version: Monotonically increasing plan version number.
    """
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO study_plans (conv_id, state_json, version, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(conv_id) DO UPDATE SET
                state_json = excluded.state_json,
                version    = excluded.version,
                updated_at = excluded.updated_at
            """,
            (conv_id, json.dumps(plan_json), version, _now()),
        )


def get_study_plan(conv_id: str) -> dict | None:
    """Return a study plan record by conversation id, or None if absent.

    Args:
        conv_id: Conversation identifier.

    Returns:
        A dict with keys ``state_json`` (parsed dict), ``version`` (int), and
        ``updated_at`` (ISO timestamp string), or ``None`` if not found.
    """
    with _cursor() as cur:
        cur.execute(
            "SELECT state_json, version, updated_at FROM study_plans WHERE conv_id = ?",
            (conv_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "state_json": json.loads(row["state_json"]),
        "version": row["version"],
        "updated_at": row["updated_at"],
    }


def delete_study_plan(conv_id: str) -> bool:
    """Delete a study plan row.  Returns True if a row was deleted.

    Args:
        conv_id: Conversation identifier.

    Returns:
        ``True`` if the row existed and was deleted; ``False`` otherwise.
    """
    with _cursor() as cur:
        cur.execute("DELETE FROM study_plans WHERE conv_id = ?", (conv_id,))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter()


class _ConvCreateBody(BaseModel):
    model_config = {"protected_namespaces": ()}

    title: str
    mode: str = "tutor"
    model_id: str
    # Accept ``None`` / missing field and coerce to ``"ALL"`` so frontends
    # that haven't loaded /api/books yet (or sent an empty selection) still
    # persist successfully instead of failing the POST with 422.
    book_filter: list[str] | str | None = "ALL"


@router.get("/conversations", response_model=list[ConversationDigest])
def api_list_conversations() -> list[ConversationDigest]:
    return list_conversations()


@router.post("/conversations", response_model=ConversationDigest, status_code=201)
def api_create_conversation(body: _ConvCreateBody) -> ConversationDigest:
    bf = body.book_filter
    if bf is None or (isinstance(bf, list) and len(bf) == 0):
        bf = "ALL"
    return create_conversation(
        title=body.title,
        mode=body.mode,
        model_id=body.model_id,
        book_filter=bf,
    )


@router.get("/conversations/{conv_id}")
def api_get_conversation(conv_id: str) -> dict:
    digest = get_conversation(conv_id)
    if digest is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {**digest.model_dump(), "messages": get_messages(conv_id)}


@router.delete("/conversations/{conv_id}", status_code=204, response_class=Response)
def api_delete_conversation(conv_id: str) -> Response:
    if not delete_conversation(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    cleanup_conv_collection(conv_id)
    return Response(status_code=204)


@router.get("/preferences")
def api_get_preferences() -> dict:
    with _cursor() as cur:
        cur.execute("SELECT key, value FROM prefs")
        rows = cur.fetchall()
    return {r["key"]: json.loads(r["value"]) for r in rows}


@router.patch("/preferences")
def api_patch_preferences(body: dict) -> dict:
    for key, value in body.items():
        set_pref(key, value)
    return api_get_preferences()
