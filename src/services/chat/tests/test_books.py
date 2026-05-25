"""Tests for src.services.chat.books."""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[4] / "data" / "parsed" / "manifest.json"
)
_BOOKS_DIR = Path(__file__).resolve().parents[4] / "src" / "ingestion" / "books"

_manifest_exists = pytest.mark.skipif(
    not _MANIFEST_PATH.exists(),
    reason="data/parsed/manifest.json not present in this environment",
)
_books_dir_exists = pytest.mark.skipif(
    not _BOOKS_DIR.exists(),
    reason="src/ingestion/books/ not present in this environment",
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@_manifest_exists
@_books_dir_exists
def test_list_books_returns_at_least_one() -> None:
    """list_books() must return at least one Book when yaml + manifest exist."""
    # Import inside test so the skipif markers suppress import-time errors
    from src.services.chat.books import list_books  # noqa: PLC0415

    books = list_books()
    assert len(books) >= 1, "Expected at least one book from the registry"


@_books_dir_exists
def test_collections_for_books_islp() -> None:
    """collections_for_books(['islp']) should map introduction_textbooks → ['islp']."""
    from src.services.chat.books import collections_for_books  # noqa: PLC0415

    result = collections_for_books(["islp"])
    assert result == {"introduction_textbooks": ["islp"]}


def test_get_book_nonexistent_returns_none() -> None:
    """get_book() with an unknown slug must return None, not raise."""
    from src.services.chat.books import get_book  # noqa: PLC0415

    assert get_book("nonexistent_book_xyz") is None


@_books_dir_exists
def test_collections_for_books_empty_slugs() -> None:
    """Empty slug list returns empty dict."""
    from src.services.chat.books import collections_for_books  # noqa: PLC0415

    assert collections_for_books([]) == {}


@_books_dir_exists
def test_collections_for_books_unknown_slug_ignored() -> None:
    """Unknown slugs are silently skipped; result only contains known books."""
    from src.services.chat.books import collections_for_books  # noqa: PLC0415

    result = collections_for_books(["islp", "does_not_exist_ever"])
    assert "does_not_exist_ever" not in str(result)
    assert "introduction_textbooks" in result


@_manifest_exists
@_books_dir_exists
def test_book_fields_populated() -> None:
    """Each Book must have non-empty id, title, field, collection."""
    from src.services.chat.books import list_books  # noqa: PLC0415

    for book in list_books():
        assert book.id, f"Book has empty id: {book}"
        assert book.title, f"Book '{book.id}' has empty title"
        assert book.field, f"Book '{book.id}' has empty field"
        assert book.collection.endswith("_textbooks"), (
            f"Book '{book.id}' collection '{book.collection}' missing _textbooks suffix"
        )
        assert book.image_collection.endswith("_images"), (
            f"Book '{book.id}' image_collection '{book.image_collection}' missing _images suffix"
        )


@_manifest_exists
@_books_dir_exists
def test_books_for_field_introduction() -> None:
    """books_for_field('introduction') returns only introduction-field books."""
    from src.services.chat.books import books_for_field  # noqa: PLC0415

    books = books_for_field("introduction")
    assert len(books) >= 1
    assert all(b.field == "introduction" for b in books)


@_manifest_exists
@_books_dir_exists
def test_get_book_islp() -> None:
    """get_book('islp') returns a Book with the expected slug."""
    from src.services.chat.books import get_book  # noqa: PLC0415

    book = get_book("islp")
    assert book is not None
    assert book.id == "islp"
    assert book.collection == "introduction_textbooks"
    assert book.chunks > 0
