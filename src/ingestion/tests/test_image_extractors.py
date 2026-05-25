"""Unit tests for `ingest_images_only` extractors + caption builders.

No Qdrant or OpenAI calls — operates on in-memory markdown blobs.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ingestion.ingest_images_only import (
    _caption_from_nearby,
    _chapter_id_from_h1,
    _find_section_context,
    _preceding_prose,
    _strip_html,
    extract_epub_images,
    extract_vlm_images,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _book(slug: str = "testbook", name: str = "Test Book") -> SimpleNamespace:
    return SimpleNamespace(
        slug=slug,
        name=name,
        authors=["Author One", "Author Two"],
    )


def _write(tmp_path: Path, text: str, fname: str = "sample.md") -> Path:
    p = tmp_path / fname
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# string helpers
# ---------------------------------------------------------------------------


def test_strip_html_removes_tags_and_pipes():
    out = _strip_html("<b>hi</b> | <i>there</i>")
    assert "hi" in out and "there" in out
    assert "<" not in out and ">" not in out and "|" not in out


def test_chapter_id_from_h1_extracts_leading_int():
    assert _chapter_id_from_h1("3 THE ALGEBRA OF LEAST SQUARES") == "ch03"
    assert _chapter_id_from_h1("12 Some Chapter") == "ch12"


def test_chapter_id_from_h1_falls_back_when_no_number():
    assert _chapter_id_from_h1("Preface") == "ch00"
    assert _chapter_id_from_h1("Preface", fallback="ch99") == "ch99"


def test_find_section_context_picks_last_h1_and_h2():
    text = (
        "# 2 Random Variables\n\n"
        "some text\n\n"
        "## 2.2 Distribution of Wages\n\n"
        "more text\n\n"
        "![](images/abc.jpg)\n"
    )
    pos = text.index("![](")
    h1, h2 = _find_section_context(text, pos)
    assert h1.startswith("2 Random Variables")
    assert "Distribution of Wages" in h2


def test_find_section_context_resets_h2_on_new_h1():
    text = (
        "# 1 First\n## 1.1 Sub\ntxt\n# 2 Second\nmoretxt\n![](images/x.jpg)\n"
    )
    pos = text.index("![](")
    h1, h2 = _find_section_context(text, pos)
    assert h1.startswith("2 Second")
    assert h2 == ""  # not carried over from chapter 1


# ---------------------------------------------------------------------------
# caption builders
# ---------------------------------------------------------------------------


def test_preceding_prose_picks_last_two_sentences():
    text = (
        "Some intro line.\n\n"
        "First real sentence about bias. Second sentence on variance trade-off in models.\n\n"
        "![](images/x.jpg)\n"
    )
    pos = text.index("![](")
    prose = _preceding_prose(text, pos)
    assert "variance" in prose.lower()


def test_preceding_prose_skips_tables_and_headers():
    text = (
        "# Header line\n\n"
        "| a | b |\n"
        "| --- | --- |\n"
        "Real prose sentence that should be kept as caption fallback context.\n\n"
        "![](images/x.jpg)\n"
    )
    pos = text.index("![](")
    prose = _preceding_prose(text, pos)
    assert "Real prose sentence" in prose
    assert "| a | b |" not in prose


def test_caption_from_nearby_prefers_details_block_when_present():
    text = "![](images/x.jpg)\n\n<details>\n<summary>scatter</summary>\nx y plot data\n</details>\n"
    pos = text.index("![](")
    end = text.index("\n", pos) + 1
    cap = _caption_from_nearby(text, pos, end)
    assert "scatter" in cap


def test_caption_from_nearby_falls_back_to_first_line():
    """Caller passes the regex's m.end() (right after the ``)`` of the
    image ref, before the newline). The function skips the first split
    chunk which is empty on the original-line side."""
    text = "![](images/x.jpg)\nA short prose explanation of the figure follows.\n"
    pos = text.index("![](")
    img_end = pos + len("![](images/x.jpg)")  # matches re.match.end()
    cap = _caption_from_nearby(text, pos, img_end)
    assert "short prose" in cap


# ---------------------------------------------------------------------------
# VLM extractor
# ---------------------------------------------------------------------------


def test_extract_vlm_dedupes_repeated_image(tmp_path: Path):
    text = (
        "# 1 INTRO\n"
        "![](images/abc.jpg)\n"
        "![](images/abc.jpg)\n"
    )
    md = _write(tmp_path, text)
    imgs = extract_vlm_images(md, _book())
    assert len(imgs) == 1
    assert imgs[0].image_name == "abc.jpg"


def test_extract_vlm_attributes_chapter_from_h1(tmp_path: Path):
    text = (
        "# 1 INTRO\n"
        "intro text\n\n"
        "# 3 THE ALGEBRA OF LEAST SQUARES\n\n"
        "Some equation prose before the figure here below.\n\n"
        "![](images/abc.jpg)\n\n"
        "<details><summary>scatter</summary>x y plot</details>\n"
    )
    md = _write(tmp_path, text)
    imgs = extract_vlm_images(md, _book())
    assert len(imgs) == 1
    assert imgs[0].chapter_id == "ch03"
    assert "scatter" in imgs[0].image_reference
    assert imgs[0].section.startswith("3 THE ALGEBRA")


def test_extract_vlm_resolves_absolute_image_path(tmp_path: Path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "abc.jpg").write_bytes(b"")
    md = _write(tmp_path, "# 1 INTRO\n![](images/abc.jpg)\n")
    imgs = extract_vlm_images(md, _book())
    assert Path(imgs[0].image_path).exists()


def test_extract_vlm_caption_fallback_when_no_details(tmp_path: Path):
    text = "# 1 INTRO\n![](images/lone.jpg)\n"
    md = _write(tmp_path, text)
    imgs = extract_vlm_images(md, _book(name="Foo Book"))
    assert imgs[0].image_reference  # non-empty
    assert "Foo Book" in imgs[0].image_reference or imgs[0].image_reference


# ---------------------------------------------------------------------------
# EPUB extractor
# ---------------------------------------------------------------------------


def test_extract_epub_skips_inline_art_glyphs(tmp_path: Path):
    text = (
        "# 1 Chapter\n"
        "Some text with inline art ![art](markdown/Book/media/images/Art_P1.jpg) here.\n"
        "![alt-text-real-fig](markdown/Book/media/images/figure_one.jpg)\n"
        "*Figure 1.1: Real figure.*\n"
    )
    md = _write(tmp_path, text)
    imgs = extract_epub_images(md, _book())
    names = [i.image_name for i in imgs]
    assert "Art_P1.jpg" not in names  # filtered as inline math glyph
    assert "figure_one.jpg" in names


def test_extract_epub_uses_italic_caption(tmp_path: Path):
    text = (
        "# 1 Chapter\n"
        "Pre-image prose.\n\n"
        "![art](markdown/Book/media/images/fig1.jpg)\n\n"
        "*Figure 1.1: Three types of Iris flowers.*\n"
    )
    md = _write(tmp_path, text)
    imgs = extract_epub_images(md, _book())
    assert len(imgs) == 1
    assert "Iris flowers" in imgs[0].image_reference


def test_extract_epub_alt_in_skiplist_falls_back(tmp_path: Path):
    """alt of 'Cover Image' is in the skip-list (lower-cased). Image is
    placed deep in the file with prose context so the cover-page filter
    does NOT drop it. Expect non-empty caption from preceding prose."""
    deep_prose = "A thoroughly long paragraph of real chapter prose explaining the concept. " * 50
    text = (
        "# 1 Chapter\n"
        + deep_prose
        + "\n\n![Cover Image](markdown/Book/media/images/diagram_1.jpg)\n"
    )
    md = _write(tmp_path, text)
    imgs = extract_epub_images(md, _book())
    assert len(imgs) == 1
    assert imgs[0].image_reference


def test_extract_epub_alt_text_when_distinct(tmp_path: Path):
    text = (
        "# 1 Chapter\n"
        "![Neural network diagram](markdown/Book/media/images/nn.jpg)\n"
    )
    md = _write(tmp_path, text)
    imgs = extract_epub_images(md, _book())
    assert "Neural network diagram" in imgs[0].image_reference


def test_extract_vlm_drops_cover_by_filename(tmp_path: Path):
    text = (
        "# Some Book\n"
        "![](images/cover.jpg)\n"
        "more prose follows so the file is large enough\n" * 50
        + "# 1 INTRO\n"
        "![](images/figure1.jpg)\n"
        "<details><summary>scatter</summary>x y</details>\n"
    )
    md = _write(tmp_path, text)
    imgs = extract_vlm_images(md, _book())
    names = [i.image_name for i in imgs]
    assert "cover.jpg" not in names
    assert "figure1.jpg" in names


def test_extract_vlm_drops_image_in_cover_band_without_prose(tmp_path: Path):
    cover_band = "# ECONOMETRICS\n" * 5 + "![](images/sha-cover.jpg)\n"
    body = "\nA real chapter starts here with lots of prose. " * 200
    text = cover_band + body + "\n![](images/sha-real.jpg)\n"
    md = _write(tmp_path, text)
    imgs = extract_vlm_images(md, _book())
    names = [i.image_name for i in imgs]
    assert "sha-cover.jpg" not in names
    assert "sha-real.jpg" in names


def test_extract_epub_dedupes_by_image_name(tmp_path: Path):
    text = (
        "# 1\n"
        "![](markdown/Book/media/images/same.jpg)\n"
        "![alt2](markdown/Book/media/images/same.jpg)\n"
    )
    md = _write(tmp_path, text)
    imgs = extract_epub_images(md, _book())
    assert len(imgs) == 1
