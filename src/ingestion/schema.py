"""Pydantic models for ingestion metadata.

Mirrors ingestion/reference.md schema. All fields optional except the ones
needed to address a chunk (book_slug, chapter_id, section_id).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BookMetadata(BaseModel):
    """Static, book-level info. One file per book in ingestion/books/."""

    slug: str
    name: str
    authors: list[str]
    field: str  # collection prefix, e.g. "introduction", "econometrics"
    theme: str | None = None
    edition: str | None = None
    year: int | None = None
    source_path: str
    index_terms: list[str] = Field(default_factory=list)
    bibliography: list[str] = Field(default_factory=list)


class SectionMetadata(BaseModel):
    """Per-section structured metadata. Lives in data/parsed/<book>/sections.json."""

    book_slug: str
    chapter_id: str
    section_id: str
    h1: str | None = None
    h2_path: str
    page_from: int | None = None
    page_to: int | None = None
    formulas: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    tables_html: list[str] = Field(default_factory=list)
    table_refs: list[str] = Field(default_factory=list)
    index_extended: list[str] = Field(default_factory=list)
    synopsis: str | None = None
    text: str
    char_count: int = 0


class ImageMetadata(BaseModel):
    """Per-image record. Lives in image collection in Qdrant.

    Mirrors ingestion/reference_image.md:
        book_name, authors, section, subsection (h2_path), page,
        image_name, image_reference (caption).
    """

    book_slug: str
    book_name: str
    authors: list[str]
    chapter_id: str
    section: str | None = None      # h1
    subsection: str               # h2_path
    page: int | None = None
    image_name: str               # filename only
    image_path: str               # relative path as found in markdown (e.g. imgs/...)
    image_reference: str          # FIGURE caption text


class ManifestEntry(BaseModel):
    """One row in manifest.json — tracks an ingested chapter."""

    book_slug: str
    book_name: str
    chapter_id: str
    source_path: str
    source_hash: str
    chapter_hash: str
    ingested_at: datetime
    provider: Literal["deepseek", "openai"]
    chunk_count: int
    parent_count: int
    image_count: int = 0
    qdrant_collection_text: str
    qdrant_collection_images: str = ""
    status: Literal["success", "partial", "failed"] = "success"


class Manifest(BaseModel):
    version: int = 1
    entries: list[ManifestEntry] = Field(default_factory=list)
