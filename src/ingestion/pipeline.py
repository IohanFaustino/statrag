"""Orchestrator — per-chapter ingestion into Qdrant.

Stages:
    A static  -> yaml + book.json (Claude-extracted index + bib)
    B regex   -> sections (line-stream, page state, H1 fallback) + images
    C llm     -> synopsis + index_extended per section (cached)
    D build   -> section-level chunks, 8K token cap (no parent/child)
    E persist -> Qdrant text + image collections
    F register -> manifest

Knobs:
    --limit-sections N   ingest only the first N sections (token cost control)

Monitoring: logs token histogram of produced chunks; saves stats JSON to
data/parsed/<book>/<chapter>_build_stats.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import yaml
from fastembed import SparseTextEmbedding
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from qdrant_client.models import PointStruct, SparseVector

from src.core.config import DATA_DIR, ROOT, settings
from src.ingestion import build_documents, manifest, regex_pass
from src.ingestion.llm_client import Provider
from src.ingestion.llm_enrich import enrich_sections
from src.ingestion.schema import BookMetadata, ImageMetadata, ManifestEntry
from src.core.qdrant_store import (
    IMAGE_VECTOR,
    SPARSE_VECTOR,
    TEXT_VECTOR,
    client,
    collection_names,
    ensure_image_collection,
    ensure_text_collection,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

BOOKS_DIR = ROOT / "src" / "ingestion" / "books"
_SPARSE_MODEL = "Qdrant/bm25"


def load_book_yaml(book_slug: str) -> dict:
    path = BOOKS_DIR / f"{book_slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing book config: {path}")
    return yaml.safe_load(path.read_text())


def load_book_static_metadata(book_slug: str) -> BookMetadata:
    cfg = load_book_yaml(book_slug)
    static_path = DATA_DIR / "parsed" / book_slug / "book.json"
    extra = json.loads(static_path.read_text()) if static_path.exists() else {}
    if "field" not in cfg:
        raise ValueError(
            f"Book yaml {book_slug}.yaml missing required 'field' key "
            "(collection prefix, e.g. 'introduction', 'econometrics')."
        )
    return BookMetadata(
        slug=cfg["slug"],
        name=cfg["name"],
        authors=cfg["authors"],
        field=cfg["field"],
        theme=cfg.get("theme"),
        edition=cfg.get("edition"),
        year=cfg.get("year"),
        source_path=cfg["source_path"],
        index_terms=extra.get("index_terms", []),
        bibliography=extra.get("bibliography", []),
    )


def _uuid_for(prefix: str, content: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{prefix}::{content}"))


def _persist_text(docs: list[Document], ids: list[str], collection: str) -> int:
    if not docs:
        logger.warning("No chunks to persist to %s — skipping upsert", collection)
        return 0
    ensure_text_collection(collection)
    emb_dense = OpenAIEmbeddings(
        model=settings.embedding_model, api_key=settings.openai_api_key
    )
    emb_sparse = SparseTextEmbedding(model_name=_SPARSE_MODEL)

    texts = [d.page_content for d in docs]
    logger.info("Embedding %d chunks (dense + sparse)...", len(texts))
    dense_vecs = emb_dense.embed_documents(texts)
    sparse_vecs = list(emb_sparse.embed(texts))

    points: list[PointStruct] = []
    for cid, doc, dvec, svec in zip(ids, docs, dense_vecs, sparse_vecs):
        pid = _uuid_for("c", cid)
        payload = {**doc.metadata, "text": doc.page_content, "chunk_id": cid}
        points.append(PointStruct(
            id=pid,
            vector={
                TEXT_VECTOR: dvec,
                SPARSE_VECTOR: SparseVector(
                    indices=svec.indices.tolist(),
                    values=svec.values.tolist(),
                ),
            },
            payload=payload,
        ))

    client().upsert(
        collection_name=collection, points=points, wait=True,
    )
    logger.info("Qdrant text collection %s upserted %d points", collection, len(points))
    return len(points)


def _persist_images(images: list[ImageMetadata], collection: str) -> int:
    if not images:
        return 0
    ensure_image_collection(collection)
    emb = OpenAIEmbeddings(
        model=settings.embedding_model, api_key=settings.openai_api_key
    )
    captions = [f"{img.subsection} — {img.image_reference}" for img in images]
    vecs = emb.embed_documents(captions)

    points: list[PointStruct] = []
    # `theme` injected from book metadata (not on ImageMetadata model).
    book = load_book_static_metadata(images[0].book_slug) if images else None
    theme = (book.theme if book else None) or ""
    for img, vec in zip(images, vecs):
        pid = _uuid_for("img", f"{img.book_slug}::{img.image_name}")
        payload = {**img.model_dump(), "book": img.book_slug, "theme": theme}
        points.append(PointStruct(
            id=pid, vector={IMAGE_VECTOR: vec}, payload=payload,
        ))

    # Chunked upsert: large image batches (e.g. 600+) trigger writeTimeout
    # against Qdrant. Split into smaller batches.
    BATCH = 100
    for i in range(0, len(points), BATCH):
        chunk = points[i : i + BATCH]
        client().upsert(collection_name=collection, points=chunk, wait=True)
        logger.info(
            "Qdrant image collection %s upserted batch %d/%d (%d points)",
            collection, (i // BATCH) + 1, (len(points) + BATCH - 1) // BATCH, len(chunk),
        )
    logger.info("Qdrant image collection %s upserted %d points total", collection, len(points))
    return len(points)


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
    logger.info("Saved %s", path)


def run_chapter(
    book_slug: str,
    chapter_id: str,
    *,
    provider: Provider,
    force: bool,
    limit_sections: int | None = None,
) -> dict:
    """Returns a stats dict so callers (notebooks) can inspect the run."""
    book = load_book_static_metadata(book_slug)
    cfg = load_book_yaml(book_slug)
    ch_cfg = cfg["chapters"][chapter_id]
    source = Path(book.source_path)

    raw = regex_pass.chapter_raw_text(source, ch_cfg["line_start"], ch_cfg.get("line_end"))
    chap_hash = manifest.text_hash(raw)

    if not force:
        skip, why = manifest.should_skip(book_slug, chapter_id, chap_hash)
        if skip:
            logger.info("SKIP %s/%s: %s", book_slug, chapter_id, why)
            return {"status": "skipped", "reason": why}

    sections = regex_pass.parse_chapter(
        book_slug=book_slug, chapter_id=chapter_id,
        source_path=source,
        line_start=ch_cfg["line_start"], line_end=ch_cfg.get("line_end"),
        chapter_title=ch_cfg.get("title", ""),
    )
    if limit_sections is not None:
        sections = sections[: limit_sections]
        logger.info("Limit-sections active: keeping first %d", len(sections))

    sections = enrich_sections(sections, provider=provider, existing_index=book.index_terms)
    _save_json(DATA_DIR / "parsed" / book_slug / f"{chapter_id}_sections.json",
               [s.model_dump() for s in sections])

    images = regex_pass.extract_images(
        sections,
        book_slug=book.slug, book_name=book.name, authors=book.authors,
        book_source_path=source,
    )
    _save_json(DATA_DIR / "parsed" / book_slug / f"{chapter_id}_images.json",
               [i.model_dump() for i in images])

    docs, ids, stats = build_documents.build(sections, book)
    _save_json(DATA_DIR / "parsed" / book_slug / f"{chapter_id}_build_stats.json",
               asdict(stats))

    text_coll, img_coll = collection_names(book.field)
    n_text = _persist_text(docs, ids, text_coll)
    n_img = _persist_images(images, img_coll)

    if limit_sections is None:
        manifest.register(ManifestEntry(
            book_slug=book_slug,
            book_name=book.name,
            chapter_id=chapter_id,
            source_path=str(source),
            source_hash=manifest.file_hash(source),
            chapter_hash=chap_hash,
            ingested_at=manifest.utcnow(),
            provider=provider,
            chunk_count=stats.n_chunks,
            parent_count=0,
            image_count=len(images),
            qdrant_collection_text=text_coll,
            qdrant_collection_images=img_coll,
            status="success",
        ))
    else:
        logger.info("limit_sections != None — skipping manifest register (preview run)")

    logger.info(
        "DONE %s/%s — sections=%d chunks=%d (split=%d oversize=%d) images=%d provider=%s",
        book_slug, chapter_id, stats.n_sections, stats.n_chunks,
        stats.split_sections, stats.n_oversize, len(images), provider,
    )
    return {
        "status": "ok",
        "sections": stats.n_sections,
        "chunks": stats.n_chunks,
        "split_sections": stats.split_sections,
        "oversize": stats.n_oversize,
        "token_histogram": stats.token_histogram,
        "token_min": stats.token_min,
        "token_max": stats.token_max,
        "token_mean": stats.token_mean,
        "images": len(images),
    }


def cmd_status() -> None:
    rows = manifest.list_books()
    if not rows:
        print("Manifest empty.")
        return
    for r in rows:
        print(f"- {r['book']} / {r['chapter']}  chunks={r['chunks']}  "
              f"provider={r['provider']}  at={r['ingested_at']}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--book")
    p.add_argument("--chapter")
    p.add_argument("--provider", choices=["openai", "deepseek"], default=settings.default_provider)
    p.add_argument("--force", action="store_true")
    p.add_argument("--limit-sections", type=int, default=None,
                   help="Ingest only the first N sections (no manifest write).")
    p.add_argument("--status", action="store_true")
    args = p.parse_args()
    if args.status:
        cmd_status()
        return 0
    if not (args.book and args.chapter):
        p.error("--book and --chapter required (or --status)")
    run_chapter(args.book, args.chapter,
                provider=args.provider, force=args.force,
                limit_sections=args.limit_sections)
    return 0


if __name__ == "__main__":
    sys.exit(main())
