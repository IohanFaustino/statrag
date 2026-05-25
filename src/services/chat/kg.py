"""Knowledge-graph persistence layer using the ``concepts_kg`` Qdrant collection.

Each concept node is stored as a single vector point (embedding of the concept
label) with payload encoding its outgoing prerequisite edges.  This enables
semantic lookup ("find concepts similar to X") in addition to id-based lookups.

Chinese-wall: imports only from ``src.core.*`` and sibling chat schemas.
ADR-003: KG persistence in Qdrant collection.
"""
from __future__ import annotations

import hashlib
import logging

import openai as _openai

from src.core.config import settings
from src.core.qdrant_store import TEXT_VECTOR, client, ensure_text_collection
from src.services.chat.schemas.output import ConceptEdge, ConceptNode

logger = logging.getLogger(__name__)

COLLECTION = "concepts_kg"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_kg() -> None:
    """Ensure the ``concepts_kg`` collection exists in Qdrant.

    Calls :func:`~src.core.qdrant_store.ensure_text_collection` which is
    idempotent.  Errors are logged but not re-raised so callers remain
    non-fatal.
    """
    try:
        ensure_text_collection(COLLECTION)
    except Exception:  # noqa: BLE001
        logger.exception("ensure concepts_kg failed")


def _point_id(label: str) -> str:
    """Derive a deterministic Qdrant point id from a concept label.

    Uses the hex digest of MD5(label.lower()) to produce a stable 32-char
    string id that is collision-resistant for the expected dataset size.

    Args:
        label: Human-readable concept label.

    Returns:
        32-character hex string.
    """
    return hashlib.md5(label.lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def upsert_concepts(nodes: list[ConceptNode], edges: list[ConceptEdge]) -> None:
    """Embed each concept label and upsert points into ``concepts_kg``.

    Edges are encoded into the ``edges_out`` payload field of the source node
    rather than as separate points.  This keeps the data model simple and
    avoids separate edge collections.

    Args:
        nodes: Concept nodes to upsert.  Labels are embedded via the
            configured OpenAI embedding model.
        edges: Directed prerequisite edges; encoded into node payloads.
    """
    _ensure_kg()
    if not nodes:
        return

    try:
        oa = _openai.OpenAI(api_key=settings.openai_api_key)
        labels = [n.label for n in nodes]
        emb_resp = oa.embeddings.create(model=settings.embedding_model, input=labels)
        emb = emb_resp.data

        # Build per-node outgoing edge index
        adj_out: dict[str, list[dict]] = {n.id: [] for n in nodes}
        for e in edges:
            adj_out.setdefault(e.from_id, []).append(
                {"to": e.to_id, "weight": e.weight}
            )

        from qdrant_client.models import PointStruct  # local import avoids top-level dep

        points = [
            PointStruct(
                id=_point_id(n.label),
                vector={TEXT_VECTOR: emb[i].embedding},
                payload={
                    "label": n.label,
                    "concept_id": n.id,
                    "source": n.source.model_dump() if n.source else None,
                    "edges_out": adj_out.get(n.id, []),
                },
            )
            for i, n in enumerate(nodes)
        ]
        client().upsert(collection_name=COLLECTION, points=points)
        logger.debug("upsert_concepts: %d points upserted to %s", len(points), COLLECTION)
    except Exception:  # noqa: BLE001
        logger.exception("upsert_concepts failed")


def fetch_concepts_by_label(label: str, *, k: int = 5) -> list[dict]:
    """Semantic nearest-neighbour lookup of concepts by label similarity.

    Embeds *label* and queries the ``concepts_kg`` collection for the *k*
    most similar concept points.

    Args:
        label: Query label string (e.g. ``"linear regression"``).
        k: Maximum number of concepts to return.

    Returns:
        List of payload dicts (each merged with its similarity ``score``).
        Returns an empty list on any error (non-fatal).
    """
    _ensure_kg()
    try:
        oa = _openai.OpenAI(api_key=settings.openai_api_key)
        vec = oa.embeddings.create(
            model=settings.embedding_model, input=label
        ).data[0].embedding
        res = client().query_points(
            collection_name=COLLECTION,
            query=vec,
            using=TEXT_VECTOR,
            limit=k,
            with_payload=True,
        )
        return [{**(p.payload or {}), "score": p.score} for p in res.points]
    except Exception:  # noqa: BLE001
        logger.debug("fetch_concepts_by_label failed (non-fatal)")
        return []
