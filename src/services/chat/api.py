"""FastAPI application entry point for the statrag chat service.

Mounts all sub-routers and exposes the SSE /api/chat endpoint.

Chinese-wall: imports only from ``src.services.chat.*``.  No ingestion imports.
"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.services.chat import books, retrieval, runs, store
from src.services.chat.llm import router as llm_router
from src.services.chat.router import stream_chat
from src.services.chat.schemas import ChatRequest

# ---------------------------------------------------------------------------
# App + middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="statrag chat", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Sub-routers
# ---------------------------------------------------------------------------

app.include_router(books.router, prefix="/api")
app.include_router(retrieval.router, prefix="/api")
app.include_router(llm_router.router, prefix="/api")
app.include_router(store.router, prefix="/api")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    """Liveness probe — always returns 200 if the process is up."""
    return {"status": "ok"}


_FIGURE_ROOTS = [
    Path("/home/iohan/Documents/Books").resolve(),
    # Broader Converters root: ingested figures live under sub-paths like
    # "Converters/Books/…" AND "Converters/Cloud based/Converters/Files/…"
    # (chollet, goodfellow, etc.). Whitelisting the parent covers both
    # without listing every per-book sub-tree.
    Path("/home/iohan/Documents/Converters").resolve(),
    # EPUB-derived figure trees (e.g. Goodfellow "Deep Learning" OEBPS media).
    Path("/home/iohan/Downloads/EPUB").resolve(),
    Path("/home/iohan/Documents/toolbox/AI_models/RAG/data").resolve(),
]
_FIGURE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

# Stored ingestion paths point at a tree that has since moved. Try these
# rewrites in order before giving up. Read-only; safe to extend.
_FIGURE_PATH_REWRITES: list[tuple[str, str]] = [
    ("/home/iohan/Documents/Books/", "/home/iohan/Documents/Converters/Books/"),
]


def _resolve_figure_path(raw: str) -> Path | None:
    """Resolve a stored figure path, applying known rewrites when the
    original location no longer exists. Returns ``None`` on failure."""
    candidates = [raw]
    for old, new in _FIGURE_PATH_REWRITES:
        if raw.startswith(old):
            candidates.append(new + raw[len(old):])
    for cand in candidates:
        try:
            return Path(cand).resolve(strict=True)
        except (OSError, RuntimeError):
            continue
    return None


@app.get("/api/figures")
def serve_figure(path: str = Query(...)) -> FileResponse:
    """Serve a figure image. Path must resolve under a whitelisted root and
    have an image extension. Prevents path traversal."""
    target = _resolve_figure_path(path)
    if target is None:
        raise HTTPException(404, "figure not found")
    if target.suffix.lower() not in _FIGURE_EXTS:
        raise HTTPException(400, "not an image")
    if not any(str(target).startswith(str(r)) for r in _FIGURE_ROOTS):
        raise HTTPException(403, "path outside allowed roots")
    mime, _ = mimetypes.guess_type(str(target))
    return FileResponse(str(target), media_type=mime or "application/octet-stream")


# ---------------------------------------------------------------------------
# SSE chat endpoint
# ---------------------------------------------------------------------------


async def chat_event_gen(req: ChatRequest):
    """Yield raw chat event dicts for a turn, persisting user + assistant rows.

    Each yielded value is the bare event dict (``{"type": ..., ...}``); SSE
    framing (``event``/``id``/``data``) is applied downstream by
    :func:`_sse_from_run` / :func:`_as_sse`.  Extracted so unit tests and the
    detached run manager (``runs.py``, §13) can iterate the generator directly.

    T02 (B1 fix): writes both user and assistant rows to SQLite when
    ``req.conversationId`` is set. Persistence failures never abort the stream.
    """
    try:
        history = None
        if req.conversationId:
            try:
                history = store.get_messages(req.conversationId)
            except Exception:  # noqa: BLE001
                history = None

        if req.conversationId:
            try:
                store.append_message(
                    conversation_id=req.conversationId,
                    role="user",
                    content=req.message,
                )
            except Exception:  # noqa: BLE001
                pass

        assistant_text_buf: list[str] = []
        collected_sources: list | None = None
        collected_figures: list | None = None
        collected_meta: dict | None = None
        # When a mode produces a structured payload (TutorAnswer w/ aspects,
        # CompareAnswer, etc.) we persist the structured dict as ``content``
        # so that reloading the conversation lets the frontend re-render the
        # rich layout rather than the raw JSON-stringified token stream.
        structured_payload: dict | None = None
        structured_schema: str | None = None

        async for ev in stream_chat(req, history=history):
            ev_type = ev.get("type", "message")
            if ev_type == "token":
                assistant_text_buf.append(ev.get("text", ""))
            elif ev_type == "paragraph_break":
                assistant_text_buf.append("\n\n")
            elif ev_type == "math_block":
                assistant_text_buf.append(f"$${ev.get('tex', '')}$$")
            elif ev_type == "structured_output":
                payload = ev.get("data")
                if isinstance(payload, dict):
                    structured_payload = payload
                    structured_schema = ev.get("schema")
            elif ev_type == "sources_full":
                collected_sources = ev.get("sources")
            elif ev_type == "figures_full":
                collected_figures = ev.get("figures")
            elif ev_type == "retrieval_meta":
                collected_meta = ev.get("meta")
            yield ev

        if req.conversationId and (structured_payload or assistant_text_buf):
            # Prefer the structured dict so the frontend can re-render aspect
            # cards / citations on reload.  Fall back to the joined raw token
            # stream when no structured payload was emitted (e.g. modes that
            # do not use response_format).
            if structured_payload is not None:
                content: dict | str = dict(structured_payload)
                if structured_schema:
                    content.setdefault("_schema", structured_schema)
            else:
                content = "".join(assistant_text_buf)
            try:
                store.append_message(
                    conversation_id=req.conversationId,
                    role="assistant",
                    content=content,
                    sources=collected_sources,
                    figures=collected_figures,
                    metadata=collected_meta,
                )
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        yield {
            "type": "error",
            "code": type(exc).__name__,
            "message": str(exc),
        }
        yield {"type": "done"}


def _frame(ev: dict) -> dict:
    """Format one raw event dict as an sse-starlette frame.

    Carries the monotonic ``seq`` (§13) both as the SSE ``id`` (for native
    EventSource reconnection) and inside ``data`` (the fetch-based client reads
    it from the JSON payload to track ``lastSeq``).
    """
    frame = {"event": ev.get("type", "message"), "data": json.dumps(ev)}
    if "seq" in ev:
        frame["id"] = str(ev["seq"])
    return frame


async def _as_sse(source) -> AsyncIterator[dict]:
    """Frame a raw-event async generator directly (no run manager).

    Used for the ephemeral, non-persisted path (no ``conversationId``), which
    keeps the legacy connection-bound behaviour.
    """
    async for ev in source:
        yield _frame(ev)


async def _sse_from_run(conv_id: str, after: int = 0) -> AsyncIterator[dict]:
    """Subscribe to a detached run and frame its events as SSE (§13)."""
    async for ev in runs.subscribe(conv_id, after_seq=after):
        yield _frame(ev)


@app.post("/api/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    """Start (or attach to) a chat turn and stream its SSE response.

    With a ``conversationId`` the turn runs as a **detached, resumable run**
    (§13): generation survives client disconnect and is replayable via
    ``GET /api/chat/{conv_id}/stream``.  Without one, the legacy
    connection-bound stream is used (ephemeral, not persisted).

    Event types (in order): ``meta``, ``token``, ``paragraph_break``,
    ``math_block``, ``figure``, ``source_chip``, ``sources_full``,
    ``figures_full``, ``retrieval_meta``, ``usage``, ``done`` (or
    ``error`` + ``done``).  Every event carries a monotonic ``seq``.
    """
    conv_id = req.conversationId
    if not conv_id:
        return EventSourceResponse(_as_sse(chat_event_gen(req)), ping=15)
    runs.start_run(conv_id, lambda: chat_event_gen(req))
    return EventSourceResponse(_sse_from_run(conv_id, after=0), ping=15)


@app.get("/api/chat/{conv_id}/stream")
async def chat_resume(conv_id: str, after: int = 0) -> EventSourceResponse:
    """Resume an in-flight or finished run, replaying events after ``after``.

    Returns an immediately-closing stream when no run exists for the
    conversation (the client falls back to the persisted transcript).
    """
    return EventSourceResponse(_sse_from_run(conv_id, after=after), ping=15)


@app.get("/api/chat/{conv_id}/status")
async def chat_status(conv_id: str) -> dict:
    """Resume handshake: ``{exists, active, done, seq}`` for the run (§13)."""
    return runs.status(conv_id)


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "src.services.chat.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
