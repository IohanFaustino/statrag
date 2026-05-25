"""Image-only ingest for new VLM-format markdown.

Skips text-side entirely. Reads ``vlm/<book>.md``, finds every
``![](images/<sha>.jpg)`` reference, extracts caption from the nearest
``<details><summary>...</summary>...</details>`` block (or surrounding
prose fallback), embeds the caption, upserts to ``<field>_images``.

Usage:
    .venv/bin/python -m src.ingestion.ingest_images_only \
        --book hansen \
        --md "/home/iohan/Documents/Converters/.../vlm/2022_Hansen.md"

Idempotent: image IDs are deterministic (UUID5 of book_slug + image_name).
Re-running upserts the same IDs.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from src.ingestion.pipeline import (
    _persist_images,
    load_book_static_metadata,
)
from src.core.qdrant_store import collection_names
from src.ingestion import manifest
from src.ingestion.schema import ImageMetadata, ManifestEntry

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_RE_IMG_REF = re.compile(r"!\[\]\((images/[^)]+\.(?:jpg|jpeg|png))\)")
# EPUB-style: `![alt](markdown/<Book Title>/media/.../<file>.jpg)`
_RE_IMG_REF_EPUB = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<path>markdown/[^)]+?\.(?:jpg|jpeg|png))\)"
)
_RE_ITALIC_CAPTION = re.compile(r"^\*([^*\n][^\n]+?)\*\s*$", re.MULTILINE)
_RE_HEADER = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
_RE_DETAILS = re.compile(
    r"<details>\s*<summary>([^<]*)</summary>(.*?)</details>",
    re.DOTALL,
)
_RE_HTML_TAG = re.compile(r"<[^>]+>")

# Cover-page heuristic: image in first ~3% of the file with a section
# header consisting only of upper-case words / known title fragments and
# no real prose before it.
_COVER_BAND_FRACTION = 0.03
_COVER_NAME_HINTS = (
    "cover", "title", "front", "frontmatter", "frontispiece", "endpaper",
)


def _strip_html(s: str) -> str:
    return _RE_HTML_TAG.sub(" ", s).replace("|", " ").strip()


def _is_cover_image(
    text: str,
    char_pos: int,
    image_name: str,
    section: str,
) -> bool:
    """Drop title-page / cover / endpaper images.

    Filters when ANY of:
      - filename hints at a cover (``cover``, ``title``, ``frontmatter`` …)
      - image is in the first ``_COVER_BAND_FRACTION`` of the file AND
        no real prose has appeared yet
    """
    lname = image_name.lower()
    if any(h in lname for h in _COVER_NAME_HINTS):
        return True
    total = max(len(text), 1)
    if char_pos / total > _COVER_BAND_FRACTION:
        return False
    # In the cover band: check whether any sentence-like prose preceded.
    prefix = text[:char_pos]
    # Strip headers and image markers from prefix and look for "real" prose.
    prose_lines = [
        ln.strip()
        for ln in prefix.split("\n")
        if ln.strip()
        and not ln.strip().startswith("#")
        and not ln.strip().startswith("![")
        and not ln.strip().startswith("<")
        and not ln.strip().startswith("|")
        and len(ln.strip()) >= 40
    ]
    return len(prose_lines) == 0


def _find_section_context(text: str, char_pos: int) -> tuple[str, str]:
    """Return (h1, h2) — last ``# `` and ``## `` headers before *char_pos*."""
    prefix = text[:char_pos]
    h1, h2 = "", ""
    for m in re.finditer(r"^(#{1,3})\s+(.+)$", prefix, re.MULTILINE):
        depth = len(m.group(1))
        title = m.group(2).strip()
        if depth == 1:
            h1 = title
            h2 = ""
        elif depth == 2:
            h2 = title
        elif depth == 3 and not h2:
            h2 = title
    return h1, h2


def _chapter_id_from_h1(h1: str, fallback: str = "ch00") -> str:
    """Best-effort chapter id from h1 text like ``# 3 THE ALGEBRA OF…`` →
    ``ch03``. Falls back to *fallback*."""
    m = re.match(r"^\s*(\d{1,3})\b", h1)
    if not m:
        return fallback
    n = int(m.group(1))
    return f"ch{n:02d}"


def _preceding_prose(text: str, img_start: int, lookback_chars: int = 1200) -> str:
    """Last 1-2 non-trivial prose sentences before the image. Skips
    headers, image refs, html tags, and short table rows."""
    window = text[max(0, img_start - lookback_chars) : img_start]
    lines = window.split("\n")[::-1]  # walk backwards
    picks: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("!["):
            break  # hit a previous image
        if s.startswith("#"):
            continue
        if s.startswith("<") and s.endswith(">"):
            continue
        if s.startswith("|") or s.startswith("---"):
            continue
        if len(s) < 20:
            continue
        picks.append(_strip_html(s))
        if sum(len(p) for p in picks) > 200:
            break
    if not picks:
        return ""
    prose = " ".join(reversed(picks))
    # Last 1-2 sentences only.
    sentences = re.split(r"(?<=[.!?])\s+", prose)
    tail = " ".join(sentences[-2:]).strip()
    return tail[:300]


def _caption_from_nearby(text: str, img_start: int, img_end: int, lookahead_chars: int = 1500) -> str:
    """Compose a richer caption from preceding prose + nearest
    ``<details><summary>...</summary>...</details>`` block (VLM dump).
    """
    parts: list[str] = []
    prose = _preceding_prose(text, img_start)
    if prose:
        parts.append(prose)

    window = text[img_end : img_end + lookahead_chars]
    det = _RE_DETAILS.search(window)
    if det:
        summary = det.group(1).strip()
        body = _strip_html(det.group(2))
        body = " ".join(body.split())[:200]
        if summary:
            parts.append(summary)
        if body and body.lower() not in summary.lower():
            parts.append(body)

    if not parts:
        # Last resort: first prose line after the image.
        lines = window.split("\n")[1:11]
        for ln in lines:
            s = ln.strip()
            if s and not s.startswith(("![", "#", "<", "|", "---")):
                parts.append(s[:240])
                break

    caption = " — ".join(p for p in parts if p)
    return caption[:600]


def extract_epub_images(md_path: Path, book) -> list[ImageMetadata]:
    """EPUB-style ingest: refs look like
    ``![alt](markdown/<Title>/media/.../*.jpg)`` and captions appear as
    the next italicised single-line paragraph (``*Figure x.x: ...*``).
    Skips tiny ``Art_P*`` inline-math snippets — those are equation
    glyphs, not figures."""
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    out: list[ImageMetadata] = []
    seen_names: set[str] = set()
    book_dir = md_path.parent
    for m in _RE_IMG_REF_EPUB.finditer(text):
        rel = m.group("path")
        alt = (m.group("alt") or "").strip()
        image_name = Path(rel).name
        # Skip inline-math art (e.g. ``Art_P1234.jpg``) when alt is just
        # "art" — these are equation glyphs, not document figures.
        if image_name.lower().startswith("art_p") and alt.lower() in ("art", ""):
            continue
        if image_name in seen_names:
            continue
        seen_names.add(image_name)

        char_pos = m.start()
        h1, h2 = _find_section_context(text, char_pos)
        chapter_id = _chapter_id_from_h1(h1, fallback="ch00")
        section = h1 or book.name
        subsection = h2 or h1 or book.name

        if _is_cover_image(text, char_pos, image_name, section):
            continue

        # Caption: italic-line within next ~30 lines, or alt text, or
        # preceding prose fallback.
        window = text[m.end() : m.end() + 1500]
        cap_m = _RE_ITALIC_CAPTION.search(window)
        if cap_m:
            caption = cap_m.group(1).strip()
        elif alt and alt.lower() not in ("art", "image", "cover image"):
            caption = alt
        else:
            caption = _preceding_prose(text, char_pos) or f"Figure from {book.name}"
        caption = caption[:600]

        abs_path = str((book_dir / rel).resolve())
        out.append(ImageMetadata(
            book_slug=book.slug,
            book_name=book.name,
            authors=book.authors,
            chapter_id=chapter_id,
            section=section,
            subsection=subsection,
            page=None,
            image_name=image_name,
            image_path=abs_path,
            image_reference=caption,
        ))
    logger.info("Extracted %d unique EPUB image refs from %s", len(out), md_path)
    return out


def extract_vlm_images(md_path: Path, book) -> list[ImageMetadata]:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    out: list[ImageMetadata] = []
    seen_names: set[str] = set()
    for m in _RE_IMG_REF.finditer(text):
        img_path_rel = m.group(1)  # "images/<sha>.jpg"
        image_name = Path(img_path_rel).name
        if image_name in seen_names:
            # Dedup: same file referenced twice → keep first.
            continue
        seen_names.add(image_name)

        char_pos = m.start()
        h1, h2 = _find_section_context(text, char_pos)
        chapter_id = _chapter_id_from_h1(h1, fallback="ch00")
        section = h1 or book.name
        subsection = h2 or h1 or book.name

        if _is_cover_image(text, char_pos, image_name, section):
            continue

        caption = _caption_from_nearby(text, m.start(), m.end())
        if not caption:
            caption = f"Figure from {book.name}"

        abs_path = str((md_path.parent / img_path_rel).resolve())
        out.append(ImageMetadata(
            book_slug=book.slug,
            book_name=book.name,
            authors=book.authors,
            chapter_id=chapter_id,
            section=section,
            subsection=subsection,
            page=None,
            image_name=image_name,
            image_path=abs_path,
            image_reference=caption,
        ))
    logger.info("Extracted %d unique image refs from %s", len(out), md_path)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, help="Book slug from src/ingestion/books/")
    parser.add_argument("--md", required=True, help="Path to vlm/<book>.md")
    parser.add_argument(
        "--format", choices=["vlm", "epub", "auto"], default="auto",
        help="Markdown format. 'vlm' = new VLM output (images/<sha>.jpg + "
             "<details> captions). 'epub' = converted-EPUB style "
             "(markdown/<title>/media/.../*.jpg + italic captions). "
             "'auto' inspects the first image ref to decide.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Extract + report, do NOT upsert to Qdrant",
    )
    args = parser.parse_args()

    book = load_book_static_metadata(args.book)
    md_path = Path(args.md)
    if not md_path.exists():
        logger.error("Missing markdown: %s", md_path)
        return 2

    fmt = args.format
    if fmt == "auto":
        head = md_path.read_text(encoding="utf-8", errors="ignore")[:50000]
        fmt = "epub" if "](markdown/" in head else "vlm"
        logger.info("Auto-detected format: %s", fmt)

    if fmt == "epub":
        images = extract_epub_images(md_path, book)
    else:
        images = extract_vlm_images(md_path, book)
    if not images:
        logger.warning("No image references found in %s", md_path)
        return 1

    _, img_coll = collection_names(book.field)
    logger.info(
        "Book=%s field=%s target_collection=%s images=%d dry_run=%s",
        args.book, book.field, img_coll, len(images), args.dry_run,
    )

    # Sanity: how many image files actually exist on disk?
    missing = [i for i in images if not Path(i.image_path).exists()]
    if missing:
        logger.warning(
            "%d image files referenced in markdown do not exist on disk; first 3 missing: %s",
            len(missing),
            [i.image_path for i in missing[:3]],
        )

    if args.dry_run:
        for img in images[:3]:
            logger.info(
                "SAMPLE chapter=%s section=%r caption=%r",
                img.chapter_id, img.section[:60] if img.section else "", img.image_reference[:120],
            )
        return 0

    n = _persist_images(images, img_coll)
    logger.info("Upserted %d image points into %s", n, img_coll)

    # Register an image-only manifest entry so ``--status`` and downstream
    # tooling can see this ingest occurred. We reuse ManifestEntry with a
    # synthetic ``chapter_id`` of ``"images_only"`` and zero text counts.
    try:
        text_coll, _ = collection_names(book.field)
        manifest.register(ManifestEntry(
            book_slug=args.book,
            book_name=book.name,
            chapter_id="images_only",
            source_path=str(md_path),
            source_hash=manifest.file_hash(md_path),
            chapter_hash=manifest.text_hash(md_path.read_text(encoding="utf-8", errors="ignore")),
            ingested_at=manifest.utcnow(),
            provider="openai",
            chunk_count=0,
            parent_count=0,
            image_count=n,
            qdrant_collection_text=text_coll,
            qdrant_collection_images=img_coll,
            status="success",
        ))
    except Exception:  # noqa: BLE001
        logger.exception("manifest registration failed; ingest itself succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
