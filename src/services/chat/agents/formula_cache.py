"""Global concept→defining-equation cache (Qdrant collection ``formula_cache``).

Once a concept's verbatim equation is recovered, store it so later queries
reuse the SAME equation (consistency) without re-running vision (cost).
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

COLLECTION = "formula_cache"
_NS = uuid.UUID("00000000-0000-0000-0000-0000000fca1e")  # stable namespace for ids


@functools.lru_cache(maxsize=1)
def _oa() -> _openai.AsyncOpenAI:
    """Return (and cache) the shared AsyncOpenAI client for this process."""
    return _openai.AsyncOpenAI(api_key=settings.openai_api_key)


class RecoveredEquation(BaseModel):
    term: str
    latex: str
    citation: str = ""


def _norm(term: str) -> str:
    return re.sub(r"\s+", " ", term).strip().lower()


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


async def cache_lookup(term: str, *, threshold: float = 0.93) -> RecoveredEquation | None:
    """Semantic-lookup a recovered equation for *term*; None on miss/error."""
    try:
        if not _collection_exists(COLLECTION):
            return None
        emb = await _embed(_norm(term))
        res = _query(COLLECTION, emb, 1)
        pts = getattr(res, "points", [])
        if not pts or (pts[0].score or 0.0) < threshold:
            return None
        pl = pts[0].payload or {}
        if not pl.get("latex"):
            return None
        return RecoveredEquation(term=pl.get("term", term), latex=pl["latex"], citation=pl.get("citation", ""))
    except Exception:  # noqa: BLE001
        logger.exception("formula cache lookup failed for %s", term)
        return None


async def cache_write(term: str, latex: str, citation: str) -> None:
    """Best-effort upsert; overwrites by stable id (normalized term)."""
    if not latex:
        return
    try:
        emb = await _embed(_norm(term))
        pid = str(uuid.uuid5(_NS, _norm(term)))
        _upsert(COLLECTION, pid, emb, {"term": term, "latex": latex, "citation": citation})
    except Exception:  # noqa: BLE001
        logger.exception("formula cache write failed for %s", term)
