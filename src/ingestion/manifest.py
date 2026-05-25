"""Manifest: registry of (book, chapter) tuples already ingested.

Persisted as JSON in `data/parsed/manifest.json`. Versioned (not gitignored).

Skip rule:
    (same book_slug, chapter_id) AND (chapter_hash unchanged) AND (status=success)
    -> skip pipeline (saves regex+LLM+embed cost)

If chapter_hash changed -> previous entry is removed; re-ingest occurs.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.core.config import DATA_DIR
from src.ingestion.schema import Manifest, ManifestEntry

logger = logging.getLogger(__name__)

MANIFEST_PATH: Path = DATA_DIR / "parsed" / "manifest.json"


def file_hash(path: Path) -> str:
    """md5 of full file contents."""
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"md5:{h.hexdigest()}"


def text_hash(text: str) -> str:
    """md5 of a text slice (a chapter)."""
    return f"md5:{hashlib.md5(text.encode('utf-8')).hexdigest()}"


def load() -> Manifest:
    if not MANIFEST_PATH.exists():
        return Manifest()
    with MANIFEST_PATH.open() as f:
        return Manifest.model_validate(json.load(f))


def save(manifest: Manifest) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w") as f:
        json.dump(manifest.model_dump(mode="json"), f, indent=2, default=str)


def should_skip(
    book_slug: str, chapter_id: str, chapter_hash_value: str
) -> tuple[bool, str]:
    """Return (skip, reason)."""
    m = load()
    for e in m.entries:
        if e.book_slug == book_slug and e.chapter_id == chapter_id:
            if e.chapter_hash == chapter_hash_value and e.status == "success":
                return True, (
                    f"already ingested at {e.ingested_at.isoformat()} "
                    f"(provider={e.provider}, chunks={e.chunk_count})"
                )
            return False, "chapter content changed or previous run not success"
    return False, "not in manifest"


def register(entry: ManifestEntry) -> None:
    """Insert or replace (book_slug, chapter_id) entry."""
    m = load()
    m.entries = [
        e for e in m.entries
        if not (e.book_slug == entry.book_slug and e.chapter_id == entry.chapter_id)
    ]
    m.entries.append(entry)
    save(m)
    logger.info(
        "Manifest updated: %s/%s (%d chunks, %d parents, %s)",
        entry.book_slug, entry.chapter_id, entry.chunk_count,
        entry.parent_count, entry.status,
    )


def list_books() -> list[dict[str, str | int]]:
    """Summary for CLI: which books/chapters are indexed."""
    m = load()
    return [
        {
            "book": e.book_name,
            "chapter": e.chapter_id,
            "chunks": e.chunk_count,
            "provider": e.provider,
            "ingested_at": e.ingested_at.isoformat(),
        }
        for e in m.entries
    ]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
