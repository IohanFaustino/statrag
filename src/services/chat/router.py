"""v2 chat router — feature-flagged dispatcher between v1 orchestrator and v2 modes.

The router is the single entry point called by ``api.py`` for SSE chat. When
``req.mode`` is listed in ``settings.use_v2_modes`` the request is routed to
the v2 LangChain/LangGraph implementation; otherwise it falls back to the v1
``orchestrator.stream_chat`` for zero-risk staged rollout.

For each v2 mode, the router also adapts the LangGraph event stream into the
v1 SSE schema (``meta`` / ``token`` / ``sources_full`` / ``done``) so the
frontend ships unchanged during Phase 1.

Chinese-wall: imports only from ``src.core.*`` and sibling ``src.services.chat.*``.
ADR-006: this module replaces the dispatch logic scattered across
``orchestrator.stream_chat`` once all 11 modes are migrated.
"""
from __future__ import annotations

import json
import os
import time
from typing import AsyncIterator

from src.core.config import settings
from src.services.chat.schemas import ChatRequest


def _reconcile_tutor_citations(payload: dict) -> dict:
    """T22 (E6): renumber tutor `[N]` markers so they line up with the
    citations array.

    Defensive post-processing: the LLM occasionally uses the retrieve
    tool's `rank` (1..10) as the inline marker — but the `citations`
    array only contains the chunks the LLM actually cited. Result: the
    UI's pill lookup fails for markers like `[6]` when only 4 citations
    exist.

    Strategy: walk `text` in order, collect unique marker numbers as
    they first appear, build a remapping `original -> 1, 2, 3, …`, and
    rewrite both `text` and `citations[i].index`. Citations not
    referenced inline are dropped (they would never render as a pill
    anyway). Markers without a matching citation are stripped.
    """
    if not isinstance(payload, dict):
        return payload
    text = payload.get("text") or ""
    citations = payload.get("citations") or []
    if not text or not isinstance(text, str) or not isinstance(citations, list) or not citations:
        return payload

    import re

    # Original-index -> citation dict, keyed by index.
    by_idx: dict[int, dict] = {}
    for c in citations:
        if isinstance(c, dict) and isinstance(c.get("index"), int):
            by_idx[c["index"]] = c

    # Walk text in order; record unique marker numbers.
    marker_re = re.compile(r"\[(\d+)\]")
    new_text_chunks: list[str] = []
    remap: dict[int, int] = {}
    next_new = 1
    cursor = 0
    drop_markers: set[int] = set()
    for m in marker_re.finditer(text):
        new_text_chunks.append(text[cursor:m.start()])
        original = int(m.group(1))
        if original not in by_idx:
            drop_markers.add(original)
        else:
            if original not in remap:
                remap[original] = next_new
                next_new += 1
            new_text_chunks.append(f"[{remap[original]}]")
        cursor = m.end()
    new_text_chunks.append(text[cursor:])
    new_text = "".join(new_text_chunks)

    # Drop orphan markers (no matching citation) by removing them
    # entirely — we couldn't render a pill anyway.
    if drop_markers:
        for orig in drop_markers:
            new_text = re.sub(rf"\[{orig}\]", "", new_text)

    # Rewrite citations: keep only those cited, renumbered.
    new_citations: list[dict] = []
    for original_idx, new_idx in sorted(remap.items(), key=lambda kv: kv[1]):
        c = dict(by_idx[original_idx])
        c["index"] = new_idx
        new_citations.append(c)

    payload = dict(payload)
    payload["text"] = new_text
    payload["citations"] = new_citations
    return payload


def _v2_enabled_for(mode_id: str) -> bool:
    """Return True if *mode_id* is in ``settings.use_v2_modes``."""
    enabled = settings.parsed_use_v2_modes()
    return mode_id in enabled or "*" in enabled


async def _v1_passthrough(req: ChatRequest, history: list[dict] | None):
    """Defer to the legacy v1 orchestrator without modification."""
    from src.services.chat import orchestrator as _v1  # noqa: PLC0415

    async for event in _v1.stream_chat(req, history):
        yield event


async def _tutor_v2(req: ChatRequest, history: list[dict] | None):
    """v2 tutor mode via LangChain ``create_agent`` + adapter to v1 SSE schema.

    Streams token deltas via ``stream_mode="messages"`` and collects retrieve
    tool-call results via ``stream_mode="updates"`` so the frontend receives
    the familiar ``sources_full`` event after the response completes.
    """
    from src.services.chat.mode_impls.tutor import build_agent  # noqa: PLC0415

    agent = await build_agent()
    t0 = time.time()

    configurable = {"thread_id": req.conversationId or f"anon-{int(t0)}"}
    # T13-F: user-controllable temperature reaches the LLM via model_kwargs.
    if req.temperature is not None:
        configurable["model_kwargs"] = {"temperature": req.temperature}
    config = {
        "configurable": configurable,
        "recursion_limit": 10,
    }
    inp = {"messages": [{"role": "user", "content": req.message}]}

    yield {
        "type": "meta",
        "mode": req.mode,
        "books": [],
        "sourceCount": 0,
        "latencyMs": int((time.time() - t0) * 1000),
        "model": req.model,
    }

    collected_sources: list[dict] = []
    structured_payload: dict | None = None
    completion_chars = 0
    try:
        async for kind, payload in agent.astream(
            inp, config=config, stream_mode=["messages", "updates"]
        ):
            if kind == "messages":
                msg, _meta = payload
                content = getattr(msg, "content", None)
                if isinstance(content, str) and content:
                    completion_chars += len(content)
                    yield {"type": "token", "text": content}
            elif kind == "updates":
                if not isinstance(payload, dict):
                    continue
                for _node_name, delta in payload.items():
                    if not isinstance(delta, dict):
                        continue
                    msgs = delta.get("messages") or []
                    for m in msgs:
                        if getattr(m, "type", None) == "tool" and getattr(m, "name", "") == "retrieve":
                            try:
                                tool_payload = json.loads(m.content)
                            except Exception:  # noqa: BLE001
                                continue
                            if isinstance(tool_payload, list):
                                collected_sources.extend(tool_payload)
                    # T13-E: capture TutorAnswer structured_response when present.
                    structured = delta.get("structured_response")
                    if structured is not None:
                        if hasattr(structured, "model_dump"):
                            structured_payload = structured.model_dump()
                        elif isinstance(structured, dict):
                            structured_payload = structured
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
        yield {"type": "done"}
        return

    # T13-E: emit structured_output when the agent produced a TutorAnswer.
    if structured_payload is not None:
        # T22 (E6): defensively reconcile inline `[N]` markers with the
        # citations array. The LLM occasionally numbers markers using
        # the retrieve tool's `rank` (1..10) instead of a 1-based
        # citation index. Renumber so every marker resolves.
        structured_payload = _reconcile_tutor_citations(structured_payload)
        yield {
            "type": "structured_output",
            "schema": "TutorAnswer",
            "data": structured_payload,
        }

    if collected_sources:
        yield {"type": "sources_full", "sources": collected_sources}

    yield {
        "type": "retrieval_meta",
        "meta": {
            "rewrittenQuery": req.message[:300],
            "embedding": settings.embedding_model,
            "retrievalMs": int((time.time() - t0) * 1000),
            "collections": [],
            "filter": "v2-tutor",
            "topK": 5,
            "scoreThreshold": 0.0,
            "mode": "v2-tutor (create_agent + retrieve tool)",
        },
    }
    yield {
        "type": "usage",
        "durationMs": int((time.time() - t0) * 1000),
        "promptChars": len(req.message or ""),
        "completionChars": completion_chars,
        "estTokens": (len(req.message or "") + completion_chars) // 4,
    }
    yield {"type": "done"}


async def stream_chat(
    req: ChatRequest,
    history: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """Dispatch an SSE chat request to v1 or v2 based on per-mode feature flag.

    Args:
        req: Incoming chat request.
        history: Optional prior conversation messages (each ``{"role", "content"}``).
            For v2 modes the checkpointer also holds history; this argument
            stays for v1 compatibility.

    Yields:
        Event dicts matching the v1 SSE schema. See ``orchestrator.stream_chat``
        for the complete sequence.
    """
    if not _v2_enabled_for(req.mode):
        async for event in _v1_passthrough(req, history):
            yield event
        return

    if req.mode == "tutor":
        if os.environ.get("TUTOR_DEEP_MODE", "1") != "0":
            from src.services.chat.agents.deep_tutor import (  # noqa: PLC0415
                run_deep_tutor,
            )
            async for event in run_deep_tutor(req):
                yield event
            return
        async for event in _tutor_v2(req, history):
            yield event
        return

    if req.mode == "qa":
        from src.services.chat.agents.qa import run_qa  # noqa: PLC0415
        async for event in run_qa(req):
            yield event
        return

    # Unknown mode — fall through.
    async for event in _v1_passthrough(req, history):
        yield event
