"""Global concept→verbatim-formal-definition cache (Qdrant collection ``definition_cache``).

Once a concept's verbatim definition is recovered, store it so later queries
reuse the SAME definition (consistency) without re-running vision (cost).
Best-effort: any failure degrades to a cache miss / no-op.
"""
from __future__ import annotations

import functools
import logging
import re
import uuid

import openai as _openai
from pydantic import BaseModel

from src.core.config import settings
from src.core.qdrant_store import TEXT_VECTOR, client, ensure_text_collection

logger = logging.getLogger(__name__)

COLLECTION = "definition_cache"
_NS = uuid.UUID("00000000-0000-0000-0000-0000000def00")  # stable namespace for ids


@functools.lru_cache(maxsize=1)
def _oa() -> _openai.AsyncOpenAI:
    """Return (and cache) the shared AsyncOpenAI client for this process."""
    return _openai.AsyncOpenAI(api_key=settings.openai_api_key)


class RecoveredDefinition(BaseModel):
    concept: str
    kind: str = "definition"
    label: str = ""
    statement: str = ""          # VERBATIM
    book: str = ""
    book_name: str = ""
    chapter: str = ""
    section: str = ""
    page_from: int | None = None
    page_to: int | None = None
    chunkId: str = ""


def _norm(concept: str) -> str:
    return re.sub(r"\s+", " ", concept).strip().lower()


async def _embed(text: str) -> list[float]:
    return (await _oa().embeddings.create(model=settings.embedding_model, input=text[:8000])).data[0].embedding


def _collection_exists(name: str) -> bool:
    try:
        return name in {c.name for c in client().get_collections().collections}
    except Exception:  # noqa: BLE001
        return False


def _query(name: str, emb: list[float], limit: int) -> object:
    return client().query_points(collection_name=name, query=emb, using=TEXT_VECTOR,
                                 limit=limit, with_payload=True)


def _upsert(name: str, point_id: str, emb: list[float], payload: dict) -> None:
    from qdrant_client.models import PointStruct  # noqa: PLC0415
    ensure_text_collection(name)
    client().upsert(collection_name=name,
                    points=[PointStruct(id=point_id, vector={TEXT_VECTOR: emb}, payload=payload)])


async def cache_lookup(concept: str, *, threshold: float = 0.93) -> RecoveredDefinition | None:
    """Semantic-lookup a recovered definition for *concept*; None on miss/error."""
    try:
        if not _collection_exists(COLLECTION):
            return None
        emb = await _embed(_norm(concept))
        res = _query(COLLECTION, emb, 1)
        pts = getattr(res, "points", [])
        if not pts or (pts[0].score or 0.0) < threshold:
            return None
        pl = pts[0].payload or {}
        if not pl.get("statement"):
            return None
        return RecoveredDefinition(
            concept=pl.get("concept", concept),
            kind=pl.get("kind", "definition"),
            label=pl.get("label", ""),
            statement=pl.get("statement", ""),
            book=pl.get("book", ""),
            book_name=pl.get("book_name", ""),
            chapter=pl.get("chapter", ""),
            section=pl.get("section", ""),
            page_from=pl.get("page_from"),
            page_to=pl.get("page_to"),
            chunkId=pl.get("chunkId", ""),
        )
    except Exception:  # noqa: BLE001
        logger.exception("definition cache lookup failed for %s", concept)
        return None


async def cache_write(rd: RecoveredDefinition) -> None:
    """Best-effort upsert; overwrites by stable id (normalized concept)."""
    if not rd.statement:
        return
    try:
        emb = await _embed(_norm(rd.concept))
        pid = str(uuid.uuid5(_NS, _norm(rd.concept)))
        _upsert(COLLECTION, pid, emb, rd.model_dump())
    except Exception:  # noqa: BLE001
        logger.exception("definition cache write failed for %s", rd.concept)
