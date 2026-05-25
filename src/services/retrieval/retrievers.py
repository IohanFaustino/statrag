"""Retriever — hybrid (dense + sparse) over Qdrant section-level chunks.

After the redesign:
    - chunks are 1-per-section (split only if >8000 tokens)
    - no parent doc pattern; retriever returns the chunks directly

Fusion: Qdrant native RRF via `Prefetch` + `FusionQuery(Fusion.RRF)`.
"""
from __future__ import annotations

import logging

from fastembed import SparseTextEmbedding
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_openai import OpenAIEmbeddings
from qdrant_client.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    Prefetch,
    SparseVector,
)

from src.core.config import settings
from src.core.qdrant_store import IMAGE_VECTOR, SPARSE_VECTOR, TEXT_VECTOR, client

logger = logging.getLogger(__name__)

_SPARSE_MODEL = "Qdrant/bm25"


class QdrantHybridRetriever(BaseRetriever):
    book_slug: str | None = None
    k: int = 5

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        emb_dense = OpenAIEmbeddings(
            model=settings.embedding_model, api_key=settings.openai_api_key
        )
        emb_sparse = SparseTextEmbedding(model_name=_SPARSE_MODEL)
        dense_q = emb_dense.embed_query(query)
        sparse_q = next(emb_sparse.query_embed(query))

        flt = None
        if self.book_slug:
            flt = Filter(must=[
                FieldCondition(key="book_slug", match=MatchValue(value=self.book_slug)),
            ])

        res = client().query_points(
            collection_name=settings.qdrant_collection_text,
            prefetch=[
                Prefetch(query=dense_q, using=TEXT_VECTOR, limit=self.k * 4),
                Prefetch(
                    query=SparseVector(
                        indices=sparse_q.indices.tolist(),
                        values=sparse_q.values.tolist(),
                    ),
                    using=SPARSE_VECTOR,
                    limit=self.k * 4,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=self.k,
            query_filter=flt,
            with_payload=True,
        )
        return [
            Document(page_content=p.payload.get("text", ""), metadata=p.payload)
            for p in res.points
        ]


def build_retriever(book_slug: str | None = None) -> QdrantHybridRetriever:
    logger.info(
        "Qdrant hybrid retriever (book=%s, top_k=%d)",
        book_slug or "ANY", settings.top_k,
    )
    return QdrantHybridRetriever(book_slug=book_slug, k=settings.top_k)


def search_images(query: str, *, book_slug: str | None = None, k: int = 5) -> list[dict]:
    emb = OpenAIEmbeddings(
        model=settings.embedding_model, api_key=settings.openai_api_key
    )
    q_vec = emb.embed_query(query)
    flt = None
    if book_slug:
        flt = Filter(must=[
            FieldCondition(key="book_slug", match=MatchValue(value=book_slug)),
        ])
    res = client().query_points(
        collection_name=settings.qdrant_collection_images,
        query=q_vec,
        using=IMAGE_VECTOR,
        limit=k,
        query_filter=flt,
        with_payload=True,
    )
    return [{"score": p.score, **p.payload} for p in res.points]
