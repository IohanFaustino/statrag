"""Book registry for the chat service.

Scans ``src/ingestion/books/*.yaml`` and ``data/parsed/manifest.json`` at
import time (cached via :func:`functools.lru_cache`) to produce a stable list
of :class:`~src.services.chat.schemas.Book` objects.

Chinese-wall note: this module reads YAML and JSON as plain filesystem
artifacts; it does NOT import anything from ``src.ingestion``.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from src.services.chat.schemas import Book

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (relative to repo root, resolved at module load)
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[3]          # …/RAG
_BOOKS_DIR = _ROOT / "src" / "ingestion" / "books"
_MANIFEST_PATH = _ROOT / "data" / "parsed" / "manifest.json"

# ---------------------------------------------------------------------------
# Color palette keyed by field
# ---------------------------------------------------------------------------

_FIELD_COLORS: dict[str, str] = {
    "introduction": "#7EC8A4",
    "econometrics": "#E8A87C",
    "ml_dp": "#4F9CF9",
    "causal_inference": "#9B8FCC",
    "math": "#F0C060",
    "risk": "#FF6B7E",
}
_DEFAULT_COLOR = "#A0A0A0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_manifest() -> list[dict[str, Any]]:
    """Return manifest entries or empty list if file is absent / malformed."""
    if not _MANIFEST_PATH.exists():
        logger.warning("manifest.json not found at %s", _MANIFEST_PATH)
        return []
    try:
        data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        return data.get("entries", [])
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read manifest: %s", exc)
        return []


def _short_name(slug: str, authors: list[str]) -> str:
    """Return a display-friendly short identifier (≤12 chars)."""
    if authors:
        # Use first author's surname (last whitespace-separated token)
        surname = authors[0].split()[-1]
        candidate = surname[:12]
    else:
        candidate = slug.upper()[:12]
    return candidate


def _authors_short(authors: list[str]) -> str:
    """'First Author et al.' or just 'First Author'."""
    if not authors:
        return "Unknown"
    first = authors[0]
    return f"{first} et al." if len(authors) > 1 else first


def _edition_str(edition: Any, year: Any) -> str:
    """Human-readable edition string with graceful fallback."""
    parts: list[str] = []
    if edition:
        parts.append(f"{edition} ed.")
    if year:
        parts.append(str(year))
    return " · ".join(parts) if parts else "Unknown edition"


def _description(theme: str, authors: list[str]) -> str:
    n = len(authors)
    author_note = (
        f"{authors[0].split()[-1]} et al."
        if n > 1
        else (authors[0] if authors else "Unknown author")
    )
    return f"{theme} textbook by {author_note}."


def _build_book(raw: dict[str, Any], manifest_entries: list[dict[str, Any]]) -> Book:
    """Construct a :class:`Book` from a parsed YAML dict and manifest entries."""
    slug: str = raw.get("slug", "")
    authors: list[str] = raw.get("authors", [])
    field: str = raw.get("field", "")
    theme: str = raw.get("theme", "")
    chapters_dict: dict[str, Any] = raw.get("chapters", {})

    # Manifest aggregation for this book
    book_entries = [e for e in manifest_entries if e.get("book_slug") == slug]
    chunks = sum(e.get("chunk_count", 0) for e in book_entries)
    figures = sum(e.get("image_count", 0) for e in book_entries)
    indexed = any(e.get("status") == "success" for e in book_entries)

    return Book(
        id=slug,
        title=raw.get("name", slug),
        subtitle="",
        short=_short_name(slug, authors),
        authors=", ".join(authors),
        authorsShort=_authors_short(authors),
        edition=_edition_str(raw.get("edition"), raw.get("year")),
        field=field,
        theme=theme,
        chapters=len(chapters_dict),
        chunks=chunks,
        figures=figures,
        collection=f"{field}_textbooks",
        image_collection=f"{field}_images",
        color=_FIELD_COLORS.get(field, _DEFAULT_COLOR),
        cover=slug,
        description=_description(theme, authors),
        indexed=indexed,
        selected=True,
    )


# ---------------------------------------------------------------------------
# BookRegistry
# ---------------------------------------------------------------------------


class BookRegistry:
    """Immutable registry of all known books loaded once at startup."""

    def __init__(self) -> None:
        manifest_entries = _load_manifest()
        self._books: list[Book] = self._scan(manifest_entries)
        self._by_slug: dict[str, Book] = {b.id: b for b in self._books}

    # ------------------------------------------------------------------
    # Internal scanning
    # ------------------------------------------------------------------

    def _scan(self, manifest_entries: list[dict[str, Any]]) -> list[Book]:
        if not _BOOKS_DIR.exists():
            logger.warning("Books directory not found: %s", _BOOKS_DIR)
            return []

        books: list[Book] = []
        for yaml_path in sorted(_BOOKS_DIR.glob("*.yaml")):
            try:
                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                if not raw.get("slug"):
                    raw["slug"] = yaml_path.stem
                books.append(_build_book(raw, manifest_entries))
            except (OSError, yaml.YAMLError) as exc:
                logger.warning("Skipping %s: %s", yaml_path.name, exc)

        logger.info("BookRegistry: loaded %d books", len(books))
        return books

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def list_books(self) -> list[Book]:
        """Return all registered books."""
        return list(self._books)

    def get_book(self, slug: str) -> Book | None:
        """Return a book by slug, or None if not found."""
        return self._by_slug.get(slug)

    def books_for_field(self, field: str) -> list[Book]:
        """Return all books whose ``field`` matches *field*."""
        return [b for b in self._books if b.field == field]

    def collections_for_books(self, slugs: list[str]) -> dict[str, list[str]]:
        """Map each field-level text collection to the requested book slugs.

        Used by the retriever to know which Qdrant collections to query and
        which payload filters to apply.

        Args:
            slugs: List of book slugs the caller wants to search.

        Returns:
            Mapping of ``"<field>_textbooks"`` → list of matched slugs.
            Unknown slugs are silently ignored.
        """
        result: dict[str, list[str]] = defaultdict(list)
        for slug in slugs:
            book = self._by_slug.get(slug)
            if book is not None:
                result[book.collection].append(slug)
        return dict(result)


# ---------------------------------------------------------------------------
# Module-level singleton (cached)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _registry() -> BookRegistry:
    return BookRegistry()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_books() -> list[Book]:
    """Return all registered books."""
    return _registry().list_books()


def get_book(slug: str) -> Book | None:
    """Return a book by slug, or *None* if not found."""
    return _registry().get_book(slug)


def books_for_field(field: str) -> list[Book]:
    """Return all books whose field matches *field*."""
    return _registry().books_for_field(field)


def collections_for_books(slugs: list[str]) -> dict[str, list[str]]:
    """Map field text collections to filtered book slugs.

    Args:
        slugs: Requested book slugs.

    Returns:
        ``{"<field>_textbooks": [slug, ...], ...}``
    """
    return _registry().collections_for_books(slugs)


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter()


@router.get("/books", response_model=list[Book])
def route_list_books() -> list[Book]:
    """Return metadata for all registered books."""
    return list_books()


@router.get("/books/{slug}", response_model=Book)
def route_get_book(slug: str) -> Book:
    """Return metadata for a single book by slug."""
    book = get_book(slug)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book '{slug}' not found")
    return book
