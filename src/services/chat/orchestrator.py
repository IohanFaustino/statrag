"""SSE chat orchestrator for the chat service.

Yields dicts shaped per the SSE event schema from
``docs/upgrades/Demo/ChatSystem/design_handoff_statrag/05_rag_pipeline.md``.

Event sequence:
  meta → token* / paragraph_break* / math_block* → [structured_output]
  → sources_full → figures_full (if any) → retrieval_meta → done
  (error + done on any failure)

Chinese-wall: imports only from ``src.core.*`` and sibling
``src.services.chat.*`` modules.
"""
from __future__ import annotations

import json
import os
import time
from typing import AsyncIterator

from pydantic import ValidationError

from src.services.chat.highlights import compute_highlights
from src.services.chat.llm.base import ChatMessage, LLMError
from src.services.chat.llm.router import get_llm
from src.services.chat.memory import _resolve_strategy, build_memory_context, index_turn
from src.services.chat.modes import ModeRegistry
from src.services.chat.prompts.tutor import build_tutor_prompt
from src.services.chat.query_expansion import expand_queries
from src.services.chat.retrieval import (
    hybrid_search,
    multi_query_hybrid_search,
    search_figures,
)
from src.services.chat.rewriter import arewrite_query
from src.services.chat.schemas import ChatRequest, Figure, RetrievalMetadata, Source
from src.services.chat.schemas.output import TutorAnswer
from src.services.chat.schemas.output_repair import build_repair_prompt

# ---------------------------------------------------------------------------
# Token-stream processor (< 60 lines)
# ---------------------------------------------------------------------------

# State flags used inside _process_stream
_STATE_NORMAL = 0
_STATE_MATH = 1  # inside a $$...$$ block


async def _process_stream(
    raw: AsyncIterator[str],
) -> AsyncIterator[dict]:
    """Split a raw LLM token stream into typed SSE event dicts.

    Handles two special sequences:
    - ``\\n\\n`` → ``paragraph_break`` event (buffer flushed first).
    - ``$$...$$`` on its own → ``math_block`` event (v1: only when the full
      block arrives in the buffer without a mid-token split across the ``$$``
      markers).

    Yields dicts with keys matching the SSE event types.
    """
    buf = ""
    state = _STATE_NORMAL

    async def _flush_tokens(text: str) -> AsyncIterator[dict]:
        """Yield token events for non-empty text."""
        if text:
            yield {"type": "token", "text": text}

    async for chunk in raw:
        buf += chunk

        # Keep processing as long as there are actionable sequences in the buffer
        while True:
            if state == _STATE_NORMAL:
                # Look for the two special sequences: \n\n and $$
                para_pos = buf.find("\n\n")
                math_pos = buf.find("$$")

                if para_pos == -1 and math_pos == -1:
                    # Nothing special pending — wait for more chunks
                    break

                # Pick the nearest marker
                if para_pos != -1 and (math_pos == -1 or para_pos <= math_pos):
                    # Paragraph break wins
                    before = buf[:para_pos]
                    async for ev in _flush_tokens(before):
                        yield ev
                    yield {"type": "paragraph_break"}
                    buf = buf[para_pos + 2:]
                else:
                    # Math block open marker wins
                    before = buf[:math_pos]
                    async for ev in _flush_tokens(before):
                        yield ev
                    buf = buf[math_pos + 2:]  # consume opening $$
                    state = _STATE_MATH

            else:  # _STATE_MATH
                close_pos = buf.find("$$")
                if close_pos == -1:
                    # Closing $$ not in buffer yet — wait for more chunks
                    break
                tex = buf[:close_pos]
                yield {"type": "math_block", "tex": tex}
                buf = buf[close_pos + 2:]  # consume closing $$
                state = _STATE_NORMAL

    # Flush whatever remains
    if state == _STATE_MATH:
        # Unclosed math block — emit as raw tokens with the opening $$ prepended
        async for ev in _flush_tokens("$$" + buf):
            yield ev
    else:
        async for ev in _flush_tokens(buf):
            yield ev


# ---------------------------------------------------------------------------
# Schema validation + repair (ADR-005)
# ---------------------------------------------------------------------------


async def _validate_and_repair(
    accumulated: str,
    spec,  # ModeSpec
    llm,
    model_id: str,
) -> tuple[dict | None, str | None]:
    """Validate *accumulated* text against *spec.output_schema*.

    If validation fails once, attempt a single schema-repair call.

    Args:
        accumulated: The raw assistant text from the LLM stream.
        spec: The ``ModeSpec`` for this mode (carries ``output_schema``).
        llm: The LLM client (``BaseLLM`` instance).
        model_id: Model identifier for the repair call.

    Returns:
        ``(validated_dict, None)`` on success, or ``(None, error_str)`` on
        two consecutive failures.
    """
    schema_cls = spec.output_schema

    text = accumulated.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    # --- First attempt ---
    try:
        obj = schema_cls.model_validate_json(text)
        return obj.model_dump(), None
    except (ValidationError, Exception) as first_err:
        first_error_str = str(first_err)

    # --- Repair attempt ---
    schema_json = json.dumps(schema_cls.model_json_schema(), indent=2)
    repair_prompt = build_repair_prompt(first_error_str, schema_json, accumulated)
    repair_messages: list[ChatMessage] = [ChatMessage(role="user", content=repair_prompt)]
    repaired_text = ""
    try:
        repaired = ""
        async for chunk in llm.stream(repair_messages, model=model_id):
            repaired += chunk
        repaired_text = repaired.strip()
        if repaired_text.startswith("```"):
            lines = repaired_text.splitlines()
            repaired_text = "\n".join(lines[1:-1]) if len(lines) > 2 else repaired_text
        obj = schema_cls.model_validate_json(repaired_text)
        return obj.model_dump(), None
    except (ValidationError, Exception) as second_err:
        # Best-effort: if the answer is structurally valid and only a soft
        # FORMAT validator failed, accept it (render imperfect) rather than
        # blanking the turn. context={"skip_format_checks": True} bypasses only
        # DeepTutorAnswer's format validators; other schemas ignore it.
        for candidate in (repaired_text, text):
            if not candidate:
                continue
            try:
                obj = schema_cls.model_validate_json(
                    candidate, context={"skip_format_checks": True}
                )
                return obj.model_dump(), None
            except Exception:
                continue
        return None, str(second_err)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def stream_chat(
    req: ChatRequest,
    history: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """Yield dicts shaped per SSE event types.

    Args:
        req: The incoming chat request (see :class:`~.schemas.ChatRequest`).
        history: Optional prior messages for the conversation, each a dict
            with at least ``role`` and ``content`` keys.

    Yields:
        Event dicts. The sequence is always:
        ``meta`` → tokens/breaks/math → [``structured_output``] →
        ``sources_full`` → [``figures_full``] → ``retrieval_meta`` → ``done``.
        On any failure: ``error`` then ``done``.
    """
    t0 = time.time()

    try:
        # ------------------------------------------------------------------
        # 0. Look up ModeSpec (unknown mode → loud error, never silent tutor)
        # ------------------------------------------------------------------
        try:
            spec = ModeRegistry.get(req.mode)
        except KeyError:
            # Do NOT silently run tutor — surface the mis-route so it is caught.
            yield {
                "type": "error",
                "code": "MODE_NOT_REGISTERED",
                "message": f"Mode '{req.mode}' has no registered ModeSpec.",
            }
            yield {"type": "done"}
            return

        # ------------------------------------------------------------------
        # 1. Query rewrite
        # ------------------------------------------------------------------
        rewritten = await arewrite_query(req.message, history)

        # ------------------------------------------------------------------
        # 2. Resolve book slugs
        # ------------------------------------------------------------------
        book_filter = req.bookFilter
        if book_filter == "ALL" or book_filter == []:
            book_slugs: list[str] | None = None
        else:
            book_slugs = list(book_filter)

        # ------------------------------------------------------------------
        # 3. Query expansion + retrieval
        # ------------------------------------------------------------------
        flags = spec.retrieval_flags
        queries = await expand_queries(rewritten, flags=flags)

        sources: list[Source]
        metadata: RetrievalMetadata
        if len(queries) > 1:
            sources, metadata = await multi_query_hybrid_search(
                queries,
                book_slugs=book_slugs,
                top_k=5,
                rerank=flags.rerank,
                rerank_top_n=flags.rerank_top_n,
                adjacent_sections=flags.adjacent_sections,
            )
        else:
            sources, metadata = hybrid_search(
                rewritten,
                book_slugs=book_slugs,
                top_k=5,
                rerank=flags.rerank,
                rerank_top_n=flags.rerank_top_n,
                adjacent_sections=flags.adjacent_sections,
            )
        metadata.rewrittenQuery = " | ".join(queries)[:300]

        # ------------------------------------------------------------------
        # 4. Enrich highlights (best-effort; never block streaming)
        # ------------------------------------------------------------------
        for src in sources:
            try:
                src.highlights = compute_highlights(
                    req.message, src.chunk, max_spans=2
                )
            except Exception:  # noqa: BLE001
                pass  # highlights failure must not abort the pipeline

        # ------------------------------------------------------------------
        # 5. Retrieve figures
        # ------------------------------------------------------------------
        figures: list[Figure] = []

        try:
            figures = search_figures(rewritten, book_slugs, k=2)
        except Exception:  # noqa: BLE001
            pass  # figure search failure is non-fatal

        # ------------------------------------------------------------------
        # 6. Emit meta
        # ------------------------------------------------------------------
        unique_books: list[str] = list(dict.fromkeys(s.book for s in sources))
        yield {
            "type": "meta",
            "mode": req.mode,
            "books": unique_books,
            "sourceCount": len(sources),
            "latencyMs": int((time.time() - t0) * 1000),
            "model": req.model,
        }

        # ------------------------------------------------------------------
        # 7. Build LLM messages using mode-specific system prompt
        # ------------------------------------------------------------------
        system_text = spec.system_prompt

        # For tutor mode, append sources to the prompt as before
        # For other modes their prompts contain the RETRIEVED CONTEXT placeholder;
        # we append sources in the same rank-ordered format.
        if spec.id == "tutor":
            system_text = build_tutor_prompt(sources)
        else:
            # Append sources to any mode's system prompt
            if sources:
                blocks = ["\n\nRETRIEVED CONTEXT (rank-ordered):\n"]
                for src in sources:
                    blocks.append(
                        f"[#{src.rank}] {src.book} {src.chapter} {src.section} "
                        f"— {src.title} (score {src.score:.2f}):\n"
                        f"{src.chunk}\n---"
                    )
                system_text = system_text + "\n".join(blocks)

        messages: list[ChatMessage] = [ChatMessage(role="system", content=system_text)]

        # ------------------------------------------------------------------
        # 7b. Inject per-conversation memory context (M9)
        # ------------------------------------------------------------------
        if spec.memory != "off" and req.conversationId:
            mem_msgs = await build_memory_context(
                req.conversationId,
                req.message,
                strategy=spec.memory,
                history=history,
            )
            if mem_msgs:
                messages = [messages[0], *mem_msgs]
        elif history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and isinstance(content, str):
                    messages.append(ChatMessage(role=role, content=content))

        messages.append(ChatMessage(role="user", content=req.message))

        # ------------------------------------------------------------------
        # 8. Get LLM client
        # ------------------------------------------------------------------
        llm, model_id = get_llm(req.model)

        # ------------------------------------------------------------------
        # 9. Stream tokens with paragraph / math detection
        #    Accumulate the full text for post-stream schema validation.
        #
        # T06 (ADR-008): structured-output modes opt in to native
        # response_format constrained decoding. The OpenAI client enforces
        # the schema at decode time so the legacy repair retry effectively
        # never fires. Tutor (free-form text) bypasses this.
        # ------------------------------------------------------------------
        is_structured = spec.output_schema is not TutorAnswer
        use_rf = bool(
            is_structured
            and not os.environ.get("SCHEMA_REPAIR_LEGACY")
            and not str(model_id).lower().startswith("deepseek")
        )
        stream_kwargs: dict = {"model": model_id}
        if use_rf:
            stream_kwargs["response_format"] = spec.output_schema

        raw_stream = llm.stream(messages, **stream_kwargs)
        accumulated_text = ""

        async def _accumulating_stream(
            stream: AsyncIterator[str],
        ) -> AsyncIterator[str]:
            nonlocal accumulated_text
            async for chunk in stream:
                accumulated_text += chunk
                yield chunk

        async for ev in _process_stream(_accumulating_stream(raw_stream)):
            yield ev

        # ------------------------------------------------------------------
        # 9b. Index new turn pair into vec memory (M9)
        #     Only when the resolved strategy is vec or persist.
        # ------------------------------------------------------------------
        if req.conversationId and spec.memory in ("vec", "persist", "auto"):
            n_turns = len(history) if history else 0
            if _resolve_strategy(spec.memory, n_turns + 2) in ("vec", "persist"):
                try:
                    await index_turn(req.conversationId, "user", req.message, n_turns)
                    await index_turn(
                        req.conversationId, "assistant", accumulated_text, n_turns + 1
                    )
                except Exception:  # noqa: BLE001
                    pass  # vec indexing failure must not abort the pipeline

        # ------------------------------------------------------------------
        # 10. Schema validation + repair (structured-output modes only)
        #     Emits structured_output event before sources_full.
        # ------------------------------------------------------------------
        is_structured = spec.output_schema is not TutorAnswer
        if is_structured and accumulated_text.strip():
            validated, err = await _validate_and_repair(
                accumulated_text, spec, llm, model_id
            )
            if validated is not None:
                yield {
                    "type": "structured_output",
                    "schema": spec.output_schema.__name__,
                    "data": validated,
                }
            else:
                yield {
                    "type": "error",
                    "code": "SchemaValidationError",
                    "message": f"Output did not match {spec.output_schema.__name__}: {err}",
                }

        # ------------------------------------------------------------------
        # 11. Emit source_chip per source (inline chips) + sources_full
        # ------------------------------------------------------------------
        for s in sources:
            section_label = f"{s.chapter} {s.section}".strip() if s.chapter else s.section
            yield {
                "type": "source_chip",
                "book": s.book,
                "section": section_label,
            }
        yield {
            "type": "sources_full",
            "sources": [s.model_dump() for s in sources],
        }

        # ------------------------------------------------------------------
        # 12. Emit figures_full (only if any)
        # ------------------------------------------------------------------
        if figures:
            yield {
                "type": "figures_full",
                "figures": [f.model_dump() for f in figures],
            }

        # ------------------------------------------------------------------
        # 13. Emit retrieval_meta
        # ------------------------------------------------------------------
        yield {
            "type": "retrieval_meta",
            "meta": metadata.model_dump(),
        }

        # ------------------------------------------------------------------
        # 14. Done
        # ------------------------------------------------------------------
        yield {"type": "done"}

    except LLMError as exc:
        yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
        yield {"type": "done"}
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
        yield {"type": "done"}
