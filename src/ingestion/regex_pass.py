"""Deterministic regex pass over a markdown chapter slice.

Streaming, line-by-line:
    - tracks current page (last seen `<!-- page N -->`)
    - tracks header stack (H1..H6) -> builds h2_path
    - H1 defaults to chapter_title (from yaml) if no `#` header present
    - emits a SectionMetadata per H2+ section

Output: list[SectionMetadata]. Plus a helper `extract_images()` for the
image collection.

OCR resilience:
    - page-header bleed `### N. Statistical Learning` stripped before parsing
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from src.ingestion.schema import ImageMetadata, SectionMetadata

logger = logging.getLogger(__name__)

# --- regex library -----------------------------------------------------------

RE_HEADER = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
RE_NUMERIC_PREFIX = re.compile(r"^(\d+(?:[.-]\d+[a-z]?)+)\b\s*")
PATH_SEP = " | "
# OCR artifact filter: Python REPL outputs and code comments that the source
# markdown spuriously marks as headers. They pollute the section hierarchy.
RE_OCR_HEADER_NOISE = re.compile(
    r"^(Out\[|In\[|fit a model\b|>>>\s|\.\.\.\s)",
    re.IGNORECASE,
)
RE_PAGE = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.IGNORECASE)
RE_FORMULA_BLOCK = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
RE_FORMULA_INLINE = re.compile(r"(?<!\$)\$([^\$\n]+?)\$(?!\$)")
RE_IMG_HTML = re.compile(r'<img[^>]*src="(imgs/[^"]+)"', re.IGNORECASE)
RE_IMG_MD = re.compile(r"!\[[^\]]*\]\((imgs/[^)]+)\)")
RE_TABLE_HTML = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
RE_TABLE_REF = re.compile(r"\bTABLE\s+\d+\.\d+\.[^.\n]*", re.IGNORECASE)
RE_FIGURE_CAPTION = re.compile(
    r"<div[^>]*>\s*(FIGURE\s+\d+\.\d+\.[^<]+)</div>",
    re.IGNORECASE | re.DOTALL,
)
RE_IMG_AND_CAPTION = re.compile(
    r'<img[^>]*src="(imgs/[^"]+)"[^>]*>.*?<div[^>]*>\s*(FIGURE\s+\d+\.\d+\.[^<]+)</div>',
    re.IGNORECASE | re.DOTALL,
)
RE_PAGE_HEADER_BLEED = re.compile(
    r"^###\s+\d*\.?\s*Statistical Learning\s*$", re.MULTILINE
)


def _read_slice(path: Path, line_start: int, line_end: int | None) -> str:
    with path.open(encoding="utf-8") as f:
        lines = f.readlines()
    end = line_end if line_end is not None else len(lines)
    return "".join(lines[line_start - 1 : end])


def _peek_page_before(path: Path, line_start: int) -> int | None:
    """Find the last `<!-- page N -->` marker in lines [1, line_start-1].

    Needed because a chapter slice may start AFTER a header but BEFORE the
    first page marker inside the slice; without this, the first section's
    page_from would be None.
    """
    with path.open(encoding="utf-8") as f:
        prelude = f.readlines()[: line_start - 1]
    last_page: int | None = None
    for line in prelude:
        m = RE_PAGE.search(line)
        if m:
            last_page = int(m.group(1))
    return last_page


def _strip_ocr_bleed(text: str) -> str:
    return RE_PAGE_HEADER_BLEED.sub("", text)


def _section_id(h2_path: str) -> str:
    """Filesystem-safe id from `h2_path` (which uses ` | ` between levels).

    Pipes become double underscore so the original hierarchy is recoverable.
    """
    base = h2_path.replace(PATH_SEP, "__").replace(" ", "_").replace("/", "_")
    return re.sub(r"[^A-Za-z0-9_.]", "", base)[:120] or "root"


def _numeric_depth(header: str) -> int | None:
    """Return numeric depth (count of separators in prefix) or None if no number.

    Both dot- and dash-separated numbering are recognized; a trailing letter
    (e.g. "1-3a") does not add depth.

    Examples:
        "2.1 What Is Statistical Learning?"  -> 1
        "2.1.1 Why Estimate f?"              -> 2
        "1-1 What Is Econometrics?"          -> 1
        "1-3a Cross-Sectional Data"          -> 1
        "Prediction"                          -> None
    """
    m = RE_NUMERIC_PREFIX.match(header)
    if not m:
        return None
    return sum(1 for c in m.group(1) if c in ".-")


def _extract_artifacts(body: str) -> dict[str, list[str]]:
    formulas = RE_FORMULA_BLOCK.findall(body) + RE_FORMULA_INLINE.findall(body)
    images = RE_IMG_HTML.findall(body) + RE_IMG_MD.findall(body)
    tables = RE_TABLE_HTML.findall(body)
    table_refs = RE_TABLE_REF.findall(body)
    return {
        "formulas": [f.strip() for f in formulas if f.strip()],
        "images": list(dict.fromkeys(images)),
        "tables_html": tables,
        "table_refs": [t.strip() for t in table_refs],
    }


def parse_chapter(
    *,
    book_slug: str,
    chapter_id: str,
    source_path: Path,
    line_start: int,
    line_end: int | None,
    chapter_title: str,
) -> list[SectionMetadata]:
    """Stream-parse the chapter slice. Tracks page state line by line."""
    raw = _strip_ocr_bleed(_read_slice(source_path, line_start, line_end))

    sections: list[SectionMetadata] = []
    # numbered_stack: hierarchy backbone built from headers with a numeric
    # prefix like "2.1" or "2.1.1". Each entry is (depth, raw_text).
    numbered_stack: list[tuple[int, str]] = []
    # unnumbered_tail: headers without a numeric prefix accumulated since the
    # last numbered header. They are treated as leaf subsections of that
    # numbered ancestor.
    unnumbered_tail: list[str] = []

    current_h1: str = chapter_title
    current_page: int | None = _peek_page_before(source_path, line_start)
    page_start: int | None = current_page

    buffer: list[str] = []
    current_h2_path: str | None = None

    def current_path() -> str:
        parts = [t for _, t in numbered_stack] + unnumbered_tail
        return PATH_SEP.join(parts)

    def flush() -> None:
        nonlocal buffer, page_start
        if not current_h2_path or not buffer:
            buffer = []
            return
        body = "".join(buffer).strip()
        if len(body) < 50:
            buffer = []
            return
        arts = _extract_artifacts(body)
        sections.append(SectionMetadata(
            book_slug=book_slug,
            chapter_id=chapter_id,
            section_id=_section_id(current_h2_path),
            h1=current_h1,
            h2_path=current_h2_path,
            page_from=page_start,
            page_to=current_page,
            formulas=arts["formulas"],
            images=arts["images"],
            tables_html=arts["tables_html"],
            table_refs=arts["table_refs"],
            text=body,
            char_count=len(body),
        ))
        buffer = []

    for line in raw.splitlines(keepends=True):
        page_match = RE_PAGE.search(line)
        if page_match:
            current_page = int(page_match.group(1))

        header_match = RE_HEADER.match(line.strip())
        if not header_match:
            buffer.append(line)
            continue

        md_level = len(header_match.group(1))
        text = header_match.group(2).strip()

        # OCR noise filter — drop headers that are clearly Python REPL output
        # or code comments wrongly marked as headers in the source markdown.
        if RE_OCR_HEADER_NOISE.match(text):
            buffer.append(line)  # keep the original line as body content
            continue

        # H1 → chapter title (still respect if explicitly present).
        # Some OCR outputs flatten all headers to a single `#`. If text carries
        # a numeric prefix like "1.1 Foo", treat as a numbered section instead
        # of overwriting the chapter title.
        if md_level == 1 and _numeric_depth(text) is None:
            current_h1 = text
            continue

        depth = _numeric_depth(text)
        if depth is not None:
            # Numbered header — pops deeper-or-equal entries from backbone.
            flush()
            numbered_stack = [(d, t) for (d, t) in numbered_stack if d < depth]
            numbered_stack.append((depth, text))
            unnumbered_tail = []
            current_h2_path = current_path()
            page_start = current_page
        else:
            # Unnumbered header — append as leaf sub of last numbered ancestor.
            # If no numbered ancestor yet, treat as top-level placeholder.
            flush()
            if numbered_stack:
                unnumbered_tail.append(text)
            else:
                unnumbered_tail = [text]
            current_h2_path = current_path()
            page_start = current_page

    flush()

    logger.info(
        "Parsed %d sections from %s/%s (chapter_title=%r)",
        len(sections), book_slug, chapter_id, chapter_title,
    )
    return sections


def chapter_raw_text(
    source_path: Path, line_start: int, line_end: int | None
) -> str:
    return _read_slice(source_path, line_start, line_end)


# --- image extraction --------------------------------------------------------


def extract_images(
    sections: list[SectionMetadata],
    *,
    book_slug: str,
    book_name: str,
    authors: list[str],
    book_source_path: Path,
) -> list[ImageMetadata]:
    book_dir = book_source_path.parent
    out: list[ImageMetadata] = []
    for s in sections:
        body = s.text
        pairs = RE_IMG_AND_CAPTION.findall(body)
        paired_imgs = {p[0] for p in pairs}

        for img_path, caption in pairs:
            out.append(_make_image(
                book_slug=book_slug, book_name=book_name, authors=authors,
                section=s, img_path=img_path, caption=caption, book_dir=book_dir,
            ))

        orphan_imgs = [i for i in s.images if i not in paired_imgs]
        orphan_caps = [
            c for c in RE_FIGURE_CAPTION.findall(body)
            if not any(c in cap for _, cap in pairs)
        ]
        for img_path, caption in zip(orphan_imgs, orphan_caps):
            out.append(_make_image(
                book_slug=book_slug, book_name=book_name, authors=authors,
                section=s, img_path=img_path, caption=caption, book_dir=book_dir,
            ))

        used = {pair[0] for pair in pairs} | set(orphan_imgs[: len(orphan_caps)])
        for img_path in s.images:
            if img_path in used:
                continue
            out.append(_make_image(
                book_slug=book_slug, book_name=book_name, authors=authors,
                section=s, img_path=img_path, caption="(no caption found)",
                book_dir=book_dir,
            ))

    logger.info("Extracted %d image records", len(out))
    return out


def _make_image(
    *, book_slug: str, book_name: str, authors: list[str],
    section: SectionMetadata, img_path: str, caption: str, book_dir: Path,
) -> ImageMetadata:
    abs_path = str((book_dir / "md_assets" / img_path).resolve())
    if not Path(abs_path).exists():
        alt = (book_dir / img_path).resolve()
        if alt.exists():
            abs_path = str(alt)
    return ImageMetadata(
        book_slug=book_slug,
        book_name=book_name,
        authors=authors,
        chapter_id=section.chapter_id,
        section=section.h1,
        subsection=section.h2_path,
        page=section.page_from,
        image_name=Path(img_path).name,
        image_path=abs_path,
        image_reference=" ".join(caption.split()),
    )
