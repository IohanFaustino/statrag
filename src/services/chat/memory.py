"""Per-conversation memory namespace.

Strategy auto-escalation (when ModeSpec.memory == 'auto'):
  - turns <= 10: sliding window of last 5 user+assistant pairs
  - 10 < turns <= 30: summary compression — keep newest 5 turns intact;
    LLM-summarize older into one synthetic system message
  - turns > 30: vec — embed each turn into Qdrant collection ``conv_<id>``;
    on each new question, semantic-search the conv collection for top-3
    relevant prior turns + always include the most recent 3.

When ModeSpec.memory is a fixed strategy (sliding|summary|vec|off|persist),
use that strategy regardless of turn count. 'persist' is same as 'vec' but
the collection is NOT deleted on conv delete (used by Mode 10 study plans).

Conv collection name: f"conv_{conv_id}" (conv_id already uuid-safe).
Vectors: TEXT_VECTOR (3072d), single dense vector (no sparse for memory).
Payload: {role, content, timestamp, turn_idx}.

API:
  - async def build_memory_context(conv_id, current_query, *, strategy, history) -> list[ChatMessage]
    Returns a list of ChatMessage to prepend to the LLM messages (between
    the system prompt and the current user query).
  - def cleanup_conv_collection(conv_id) -> None
    Drops the Qdrant collection. Called from store.py's DELETE /conversations/{id}.
"""
from __future__ import annotations

import logging
from typing import Any

import openai as _openai

from src.core.config import settings
from src.core.qdrant_store import TEXT_VECTOR, client, ensure_text_collection
from src.services.chat.llm.base import ChatMessage

logger = logging.getLogger(__name__)

CONV_COLLECTION_PREFIX = "conv_"


def _conv_collection_name(conv_id: str) -> str:
    """Return the Qdrant collection name for a conversation."""
    return f"{CONV_COLLECTION_PREFIX}{conv_id}"


def _resolve_strategy(strategy: str, n_turns: int) -> str:
    """Resolve 'auto' to a concrete strategy based on turn count.

    Args:
        strategy: One of 'auto', 'sliding', 'summary', 'vec', 'persist', 'off'.
        n_turns: Number of turns already in history.

    Returns:
        Concrete strategy string.
    """
    if strategy != "auto":
        return strategy
    if n_turns <= 10:
        return "sliding"
    if n_turns <= 30:
        return "summary"
    return "vec"


def _sliding(history: list[dict[str, Any]], *, k_pairs: int = 5) -> list[ChatMessage]:
    """Return the last k_pairs user+assistant pairs from history as ChatMessage list.

    Args:
        history: List of message dicts with 'role' and 'content' keys.
        k_pairs: Number of user/assistant pairs to keep.

    Returns:
        List of ChatMessage instances.
    """
    msgs: list[ChatMessage] = []
    recent = history[-(2 * k_pairs):]
    for m in recent:
        role = m.get("role", "")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            msgs.append(ChatMessage(role=role, content=content))
    return msgs


async def _summarize_older(older: list[dict[str, Any]]) -> ChatMessage:
    """Compress the older portion of history via LLM into one synthetic system note.

    Args:
        older: List of message dicts representing the older turns.

    Returns:
        A system ChatMessage containing the summary.
    """
    if not older:
        return ChatMessage(role="system", content="")
    parts: list[str] = []
    for m in older:
        role = m.get("role", "")
        content = m.get("content")
        if isinstance(content, str):
            parts.append(f"[{role}] {content[:500]}")
    transcript = "\n".join(parts)
    prompt = (
        "Summarize the following conversation transcript into 3-4 sentences. "
        "Preserve key entities, decisions, and facts. Omit pleasantries.\n\n"
        f"{transcript}"
    )
    try:
        oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await oa.chat.completions.create(
            model=settings.openai_model_nano,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.0,
        )
        summary = resp.choices[0].message.content or ""
    except Exception:  # noqa: BLE001
        logger.exception("_summarize_older: LLM call failed, using truncated transcript")
        summary = transcript[:400]
    return ChatMessage(role="system", content=f"[Prior conversation summary]\n{summary}")


async def _vec_retrieve(conv_id: str, query: str, *, k: int = 3) -> list[ChatMessage]:
    """Embed query and semantic-search the conv_<id> collection for top-k turns.

    Args:
        conv_id: Conversation identifier.
        query: The current user query to embed.
        k: Maximum number of results to return.

    Returns:
        List of ChatMessage instances from retrieved turns.
    """
    name = _conv_collection_name(conv_id)
    try:
        existing = {c.name for c in client().get_collections().collections}
        if name not in existing:
            return []
        oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
        emb = (
            await oa.embeddings.create(model=settings.embedding_model, input=query)
        ).data[0].embedding
        res = client().query_points(
            collection_name=name,
            query=emb,
            using=TEXT_VECTOR,
            limit=k,
            with_payload=True,
        )
        msgs: list[ChatMessage] = []
        for p in res.points:
            pl = p.payload or {}
            role = pl.get("role", "user")
            content = pl.get("content", "")
            if isinstance(content, str) and content:
                msgs.append(ChatMessage(role=role, content=content))
        return msgs
    except Exception:  # noqa: BLE001
        logger.exception("vec memory retrieval failed for %s", name)
        return []


async def index_turn(
    conv_id: str,
    role: str,
    content: str,
    turn_idx: int,
) -> None:
    """Embed and upsert a turn into the conv_<id> collection.

    Called after each turn when the resolved strategy is 'vec' or 'persist'.

    Args:
        conv_id: Conversation identifier.
        role: Message role ('user' or 'assistant').
        content: Message text content.
        turn_idx: Zero-based turn index used as point ID suffix.
    """
    if not content:
        return
    name = _conv_collection_name(conv_id)
    try:
        ensure_text_collection(name)
        oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
        emb = (
            await oa.embeddings.create(
                model=settings.embedding_model,
                input=content[:8000],
            )
        ).data[0].embedding
        from qdrant_client.models import PointStruct  # noqa: PLC0415

        client().upsert(
            collection_name=name,
            points=[
                PointStruct(
                    id=f"{conv_id}-{turn_idx}",
                    vector={TEXT_VECTOR: emb},
                    payload={
                        "role": role,
                        "content": content,
                        "turn_idx": turn_idx,
                    },
                )
            ],
        )
    except Exception:  # noqa: BLE001
        logger.exception("vec memory index failed for %s", name)


def cleanup_conv_collection(conv_id: str) -> None:
    """Drop the Qdrant collection for a conversation.

    Called from store.py's DELETE /conversations/{id} route.
    No-op (with a warning log) if the collection does not exist.

    Args:
        conv_id: Conversation identifier whose collection to drop.
    """
    name = _conv_collection_name(conv_id)
    try:
        client().delete_collection(collection_name=name)
        logger.info("Dropped conv collection %s", name)
    except Exception:  # noqa: BLE001
        logger.warning(
            "cleanup_conv_collection failed for %s (may not exist)", name
        )


async def build_memory_context(
    conv_id: str | None,
    current_query: str,
    *,
    strategy: str,
    history: list[dict[str, Any]] | None,
) -> list[ChatMessage]:
    """Produce ChatMessage list to inject between system prompt and current user turn.

    Args:
        conv_id: Conversation identifier (required for vec/persist strategies).
        current_query: The current user message, used as embedding query for vec.
        strategy: Memory strategy — one of 'off', 'sliding', 'summary', 'vec',
            'persist', or 'auto'.
        history: Prior message dicts from get_messages(), each with 'role' and
            'content'. Pass None or empty list to get an empty result.

    Returns:
        List of ChatMessage to insert into the LLM messages list. Empty list
        when strategy is 'off' or history is absent.
    """
    if strategy == "off" or not history:
        return []

    n_turns = len(history)
    resolved = _resolve_strategy(strategy, n_turns)

    if resolved == "sliding":
        return _sliding(history)

    if resolved == "summary":
        cut = max(0, n_turns - 5)
        older = history[:cut]
        recent = history[cut:]
        msgs: list[ChatMessage] = []
        if older:
            msgs.append(await _summarize_older(older))
        msgs.extend(_sliding(recent, k_pairs=5))
        return msgs

    if resolved in ("vec", "persist"):
        if not conv_id:
            return _sliding(history)
        vec_msgs = await _vec_retrieve(conv_id, current_query, k=3)
        # Always include the most recent 3 turns intact (2 pairs = up to 4 msgs)
        recent = _sliding(history, k_pairs=2)
        # Deduplicate by (role, content prefix)
        seen: set[tuple[str, str]] = set()
        out: list[ChatMessage] = []
        for m in vec_msgs + recent:
            key = (m.role, m.content[:200])
            if key in seen:
                continue
            seen.add(key)
            out.append(m)
        return out

    return []
