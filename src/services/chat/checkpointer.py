"""LangGraph checkpointer factory — process-wide savers for v2 modes.

Two factories:

- :func:`get_checkpointer` — synchronous :class:`SqliteSaver` for sync
  graph invocations (tests, multi-agent setup).
- :func:`get_async_checkpointer` — :class:`AsyncSqliteSaver` for the
  router's ``agent.astream(...)`` paths. The saver's ``__init__`` calls
  ``asyncio.get_running_loop()``, so this factory MUST be invoked from
  inside an active event loop.

Both share the same SQLite file (``settings.checkpointer_db``). The sync
factory creates the LangGraph tables on first use; the async factory
runs the same table-creation routine once before constructing its saver
so an async-only process can still bootstrap.

Chinese-wall: imports only from ``src.core.*``.
ADR-007: this checkpointer replaces the custom ``memory.py`` for v2 modes.
"""
from __future__ import annotations

import threading
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.core.config import ROOT, settings

_lock = threading.Lock()

# Sync side (tests, agent graphs)
_sync_instance: SqliteSaver | None = None
_sync_cm = None

# Async side (router path)
_async_instance: AsyncSqliteSaver | None = None
_tables_ready: bool = False

_db_path: Path | None = None


def _resolve_db_path() -> Path:
    """Return the absolute path to the checkpointer SQLite file.

    ``settings.checkpointer_db`` is resolved relative to the project root
    if a relative path is supplied.
    """
    raw = Path(settings.checkpointer_db)
    return raw if raw.is_absolute() else (ROOT / raw)


def get_checkpointer() -> SqliteSaver:
    """Return the process-wide synchronous :class:`SqliteSaver` instance.

    Lazy + thread-safe. Use this for sync graphs only. Async graphs
    (``agent.astream``) must use :func:`get_async_checkpointer` instead.

    Returns:
        The shared :class:`SqliteSaver` instance.
    """
    global _sync_instance, _sync_cm, _db_path, _tables_ready

    if _sync_instance is not None:
        return _sync_instance

    with _lock:
        if _sync_instance is not None:  # double-checked
            return _sync_instance

        path = _resolve_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        _db_path = path
        _sync_cm = SqliteSaver.from_conn_string(str(path))
        _sync_instance = _sync_cm.__enter__()
        _sync_instance.setup()
        _tables_ready = True
        return _sync_instance


def _ensure_tables_exist() -> None:
    """Run :meth:`SqliteSaver.setup` once to create LangGraph tables in the
    shared SQLite file. Idempotent. Safe to call from any context."""
    global _tables_ready
    if _tables_ready:
        return
    path = _resolve_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cm = SqliteSaver.from_conn_string(str(path))
    saver = cm.__enter__()
    try:
        saver.setup()
    finally:
        cm.__exit__(None, None, None)
    _tables_ready = True


async def get_async_checkpointer() -> AsyncSqliteSaver:
    """Return the process-wide :class:`AsyncSqliteSaver` instance.

    Async because the underlying :class:`aiosqlite.Connection` must be
    awaited before being passed to the saver — the saver's
    ``__init__`` records the running loop on its internal asyncio.Lock,
    and downstream ``aget_tuple`` calls fail silently if the connection
    is still an un-awaited coroutine.

    On first call, ensures LangGraph tables exist in the shared SQLite
    file via the sync :class:`SqliteSaver`, opens an aiosqlite
    connection, and wires the saver.

    Returns:
        The shared :class:`AsyncSqliteSaver` instance.

    Raises:
        RuntimeError: When called outside a running event loop.
    """
    global _async_instance, _db_path

    if _async_instance is not None:
        return _async_instance

    # Tables can be created from sync side without an event loop.
    _ensure_tables_exist()

    # Re-check under a no-op lock: aiosqlite.connect awaits cannot run
    # under a threading.Lock so we accept the small race window. In a
    # single-loop FastAPI process this is fine — the first concurrent
    # callers contend at most once.
    if _async_instance is not None:
        return _async_instance

    import aiosqlite  # noqa: PLC0415

    path = _resolve_db_path()
    _db_path = path
    conn = await aiosqlite.connect(str(path), check_same_thread=False)
    _async_instance = AsyncSqliteSaver(conn)
    return _async_instance


def reset_checkpointer() -> None:
    """Drop the cached instances — test-only helper."""
    global _sync_instance, _sync_cm, _async_instance, _db_path, _tables_ready

    with _lock:
        if _sync_cm is not None:
            try:
                _sync_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
        _sync_instance = None
        _sync_cm = None
        _async_instance = None
        _db_path = None
        _tables_ready = False


def db_path() -> Path | None:
    """Return the resolved DB path or ``None`` if no checkpointer was created."""
    return _db_path
