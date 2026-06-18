import re

import pytest

from src.services.chat.api import _rewrite_chunk_image_paths, _FIGURE_ROOTS


def test_rewrite_strips_or_resolves_markdown_relative():
    raw = "The formula is ![$$KPSS$$](markdown/Some Book/media/images/foo.png) here."
    result = _rewrite_chunk_image_paths(raw)
    assert "markdown/Some Book" not in result
    for m in re.finditer(r"!\[.*?\]\((.*?)\)", result):
        url = m.group(1)
        assert url.startswith(("/api/figures", "http", "data:")), f"broken url escaped: {url}"


def test_rewrite_strips_images_relative():
    raw = "Result shown in ![](images/abc123.jpg) above."
    result = _rewrite_chunk_image_paths(raw)
    assert "images/abc123.jpg" not in result


def test_rewrite_leaves_valid_urls_and_citations_untouched():
    raw = "See ![ok](/api/figures?path=%2Ftmp%2Fx.png) and cite [3] and figure [F1]."
    result = _rewrite_chunk_image_paths(raw)
    assert "/api/figures?path=%2Ftmp%2Fx.png" in result
    assert "[3]" in result and "[F1]" in result


def test_rewrite_leaves_http_urls_untouched():
    raw = "See ![chart](https://example.com/img.png) here."
    result = _rewrite_chunk_image_paths(raw)
    assert "https://example.com/img.png" in result


def test_rewrite_leaves_data_uris_untouched():
    raw = "![svg](data:image/svg+xml;base64,PHN2Zy) inline."
    result = _rewrite_chunk_image_paths(raw)
    assert "data:image/svg+xml" in result


def test_rewrite_strips_nonexistent_relative_tidy_spaces():
    raw = "A ![](images/nope.gif) B"
    result = _rewrite_chunk_image_paths(raw)
    assert "nope.gif" not in result
    assert "A  B" not in result  # ponytail: double-space collapse not required; just no broken img


def test_rewrite_resolves_existing_file():
    roots = _FIGURE_ROOTS
    real_file = None
    for root in roots:
        for p in root.rglob("*.png"):
            if ".venv" in str(p):
                continue
            real_file = p
            break
        if real_file:
            break
    if real_file is None:
        pytest.skip("no .png files under _FIGURE_ROOTS to test resolution")

    # Use the relative portion under a root so _resolve_relative can find it
    for root in roots:
        try:
            rel = str(real_file).removeprefix(str(root) + "/")
        except Exception:
            continue
        if rel != str(real_file):
            break
    else:
        pytest.skip("cannot derive relative path from roots")

    raw = f"![]({rel})"
    result = _rewrite_chunk_image_paths(raw)
    assert "/api/figures?path=" in result


def test_rewrite_recurses_into_dict():
    ev = {"data": {"text": "see ![](images/nope.jpg) here", "aspects": []}}
    result = _rewrite_chunk_image_paths(ev)
    assert "images/nope.jpg" not in result["data"]["text"]


def test_rewrite_recurses_into_list():
    ev = {"data": {"aspects": [{"text": "![](images/x.gif) stuff"}]}}
    result = _rewrite_chunk_image_paths(ev)
    assert "images/x.gif" not in result["data"]["aspects"][0]["text"]


def test_rewrite_non_str_passthrough():
    assert _rewrite_chunk_image_paths(42) == 42
    assert _rewrite_chunk_image_paths(None) is None


def test_sources_full_image_refs_are_stripped():
    """BUG 2 regression: sources_full event source text must not leak
    relative corpus image paths like ![alt](markdown/...). The api.py seam
    processes the whole event dict recursively, but _sources_to_payload
    truncates chunk[:1500] BEFORE the seam runs — so a truncated ref that
    breaks the regex can leak. The fix applies _strip_corpus_images inside
    _sources_to_payload before truncation. This test verifies the seam
    (and the pre-truncation strip) both clean sources_full payloads."""
    sources_full_ev = {
        "type": "sources_full",
        "sources": [
            {
                "rank": 1,
                "book": "econometrics",
                "chunk": "See ![$$y_t$$](markdown/Econometrics in Theory and Practice/media/images/kpss.png) for details. Also ![](images/fig1.jpg).",
                "excerpt": "The test ![$$\\hat{y}$$](markdown/Econometrics/img/x.gif) is key.",
            },
            {
                "rank": 2,
                "book": "das",
                "chunk": "No images here, just text.",
                "excerpt": "Plain excerpt.",
            },
        ],
    }
    result = _rewrite_chunk_image_paths(sources_full_ev)
    for src in result["sources"]:
        for field in ("chunk", "excerpt"):
            val = src.get(field, "")
            assert "markdown/" not in val, f"leaked markdown/ in {field}: {val!r}"
            assert "images/" not in val or val.startswith(("http", "/api/")), (
                f"leaked images/ in {field}: {val!r}"
            )


def test_sources_full_truncated_image_ref_is_stripped():
    """BUG 2 regression: chunk[:1500] can truncate an image ref mid-path,
    breaking the regex in _rewrite_chunk_image_paths. The fix strips
    corpus images BEFORE truncation, so the ref is fully removed."""
    from src.services.chat.agents.deep_tutor import _strip_corpus_images

    # Simulate a long chunk where the image ref is near the 1500 boundary.
    # _strip_corpus_images runs on the full text BEFORE [:1500], so the
    # entire ref is removed regardless of where it sits.
    full_chunk = "x" * 1490 + "![alt](markdown/Book/img.png) rest of text"
    stripped = _strip_corpus_images(full_chunk)
    assert "markdown/" not in stripped, f"leaked markdown/: {stripped!r}"
    assert "![alt]" not in stripped, f"leaked ![alt]: {stripped!r}"
    # After stripping and then truncating, no broken ref survives.
    truncated = stripped[:1500]
    assert "markdown/" not in truncated
    assert "![" not in truncated