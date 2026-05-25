"""Qdrant client helpers + collection bootstrap.

One client used by ingestion + retrieval. Collections are per-field:
    <field>_textbooks  (named vectors: text dense + bm25 sparse)
    <field>_images     (single dense vector = caption embedding)

Field comes from book yaml (e.g. "introduction", "econometrics"). Collections
are auto-created on first ingest of a field.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from src.core.config import settings

logger = logging.getLogger(__name__)

DENSE_DIM = 3072
TEXT_VECTOR = "text"
SPARSE_VECTOR = "bm25"
IMAGE_VECTOR = "caption"


@lru_cache(maxsize=1)
def client() -> QdrantClient:
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=settings.qdrant_api_key or None,
        prefer_grpc=False,
    )


def collection_names(field: str) -> tuple[str, str]:
    """Return (text_collection, image_collection) for a field slug."""
    f = field.strip().lower()
    if not f:
        raise ValueError("field is required and cannot be empty")
    return f"{f}_textbooks", f"{f}_images"


def ensure_text_collection(name: str) -> None:
    c = client()
    existing = {x.name for x in c.get_collections().collections}
    if name in existing:
        return
    c.create_collection(
        collection_name=name,
        vectors_config={
            TEXT_VECTOR: VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            SPARSE_VECTOR: SparseVectorParams(index=SparseIndexParams(on_disk=False)),
        },
    )
    logger.info("Created Qdrant collection: %s", name)


def ensure_image_collection(name: str) -> None:
    c = client()
    existing = {x.name for x in c.get_collections().collections}
    if name in existing:
        return
    c.create_collection(
        collection_name=name,
        vectors_config={
            IMAGE_VECTOR: VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
        },
    )
    logger.info("Created Qdrant collection: %s", name)
