"""Build a self-contained styled-HTML ZIP for an ExtensionDigest or StoryDigest.

Chinese-wall: schemas only."""
from __future__ import annotations

import html as _html
import io
import json
import re
import zipfile

_KATEX = ("https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css")
_KATEX_JS = ("https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js")
_AUTO = ("https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js")

_CSS = """
body{font-family:Georgia,serif;max-width:46rem;margin:3rem auto;padding:0 1rem;color:#1a1a1a;line-height:1.6}
h1{font-size:1.8rem;border-bottom:2px solid #333;padding-bottom:.4rem}
h2{font-size:1.3rem;margin-top:2.2rem;color:#222}
h3{font-size:1.1rem;margin-top:1.8rem;color:#222}
.fn{font-size:.85rem;color:#444;border-left:3px solid #bbb;padding-left:.8rem;margin:.4rem 0}
.fn .src{color:#888;font-style:italic}
sup{color:#0a58ca}
.gaps{margin-top:3rem;color:#a33;font-size:.9rem}
p.story{text-align:justify}
ol.footnotes{font-size:.85rem;color:#444;padding-left:1.4rem;margin:.6rem 0}
ol.footnotes li{margin:.5rem 0}
ol.footnotes li b{color:#222}
a.wiki-ref{color:#0a58ca;text-decoration:underline}
"""

_KATEX_SCRIPT = (
    f'<script defer src="{_KATEX_JS}"></script>'
    f'<script defer src="{_AUTO}" '
    "onload=\"renderMathInElement(document.body,{delimiters:["
    "{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}]})\">"
    "</script>"
)


# ---------------------------------------------------------------------------
# Filename sanitizer
# ---------------------------------------------------------------------------

def zip_filename(book: str, chapter: str) -> str:
    """Return a sanitized ZIP filename for a digest.

    Book is preserved as-is (already slugified). Chapter is sanitized:
    ` · ` → `-`, `–`/`—` → `-`, spaces → `-`, collapse multiple `-`.

    Example::

        zip_filename("hansen-probability", "ch07 · 7.4–7.5")
        # → "hansen-probability-ch07-7.4-7.5-extended.zip"
    """
    ch = chapter
    ch = ch.replace(" · ", "-")
    ch = ch.replace("–", "-").replace("—", "-")
    ch = ch.replace(" ", "-")
    ch = re.sub(r"-{2,}", "-", ch)
    return f"{book}-{ch}-extended.zip"


# ---------------------------------------------------------------------------
# v1 ExtensionDigest renderer (unchanged)
# ---------------------------------------------------------------------------

def _render_html(digest) -> str:
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        f'<title>{_html.escape(digest.book)} {_html.escape(digest.chapter)} — extended</title>',
        f'<link rel="stylesheet" href="{_KATEX}">',
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{_html.escape(digest.book)} · {_html.escape(digest.chapter)} — Extended</h1>",
    ]
    for pt in digest.points:
        parts.append(f"<h2>{_html.escape(pt.title)}</h2>")
        parts.append(f"<p>{_html.escape(pt.curated_text)}</p>")
        for fn in pt.footnotes:
            parts.append(
                f'<div class="fn"><sup>{_html.escape(fn.marker)}</sup> {_html.escape(fn.body)} '
                f'<span class="src">({_html.escape(fn.source)} · {fn.kind})</span></div>'
            )
    if digest.unfilled_gaps:
        gaps = ", ".join(_html.escape(g) for g in digest.unfilled_gaps)
        parts.append(f'<div class="gaps">Unfilled gaps: {gaps}</div>')
    parts.append(_KATEX_SCRIPT)
    parts.append("</body></html>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# v2 StoryDigest renderer
# ---------------------------------------------------------------------------

def render_story_html(digest) -> str:
    """Return a self-contained KaTeX-capable HTML page for a StoryDigest.

    Layout: title block; then per-take a ``<section>`` with heading,
    justified story paragraph, and an ``<ol class="footnotes">`` where each
    ``CuriosityItem`` is one ``<li>`` (bold subject, body, citation labels
    — wikipedia citations rendered as ``<a href>`` links).
    """
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        f'<title>{_html.escape(digest.book)} {_html.escape(digest.chapter)} — extended</title>',
        f'<link rel="stylesheet" href="{_KATEX}">',
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{_html.escape(digest.book)} · {_html.escape(digest.chapter)} — Extended</h1>",
    ]
    for i, take in enumerate(digest.takes, 1):
        parts.append(f"<section>")
        parts.append(f"<h2>{i}. {_html.escape(take.heading)}</h2>")
        parts.append(f'<p class="story">{_html.escape(take.story)}</p>')
        if take.items:
            parts.append('<ol class="footnotes">')
            for item in take.items:
                # Build citation label(s)
                cit_parts: list[str] = []
                for c in item.citations:
                    url = getattr(c, "url", None)
                    safe_url = url if (url and url.startswith(("https://", "http://"))) else None
                    if c.kind == "wikipedia" and safe_url:
                        cit_parts.append(
                            f'<a class="wiki-ref" href="{_html.escape(safe_url)}" '
                            f'target="_blank" rel="noopener noreferrer">'
                            f'{_html.escape(c.label)}</a>'
                        )
                    else:
                        cit_parts.append(_html.escape(c.label))
                cit_html = " · ".join(cit_parts) if cit_parts else ""
                body_html = _html.escape(item.body)
                subject_html = _html.escape(item.subject)
                li = f"<li><b>{subject_html}</b> — {body_html}"
                if cit_html:
                    li += f' <span class="fn src">[{cit_html}]</span>'
                li += "</li>"
                parts.append(li)
            parts.append("</ol>")
        parts.append("</section>")
    if getattr(digest, "unfilled_subjects", None):
        subj = ", ".join(_html.escape(s) for s in digest.unfilled_subjects)
        parts.append(f'<div class="gaps">Unfilled subjects: {subj}</div>')
    parts.append(_KATEX_SCRIPT)
    parts.append("</body></html>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# ZIP builders
# ---------------------------------------------------------------------------

def build_export_zip(digest) -> bytes:
    """Return ZIP bytes: self-contained styled extension.html + sources.json."""
    sources = [
        {"point": pt.title, "marker": fn.marker, "source": fn.source, "kind": fn.kind}
        for pt in digest.points for fn in pt.footnotes
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("extension.html", _render_html(digest))
        zf.writestr("sources.json", json.dumps(sources, indent=2))
    return buf.getvalue()


def build_story_export_zip(digest) -> bytes:
    """Return ZIP bytes for a StoryDigest: story.html + sources.json."""
    sources = [
        {
            "take": take.heading,
            "subject": item.subject,
            "citation_label": c.label,
            "kind": c.kind,
            **({"url": c.url} if getattr(c, "url", None) else {}),
            **({"book_slug": c.book_slug} if getattr(c, "book_slug", None) else {}),
            **({"section_id": c.section_id} if getattr(c, "section_id", None) else {}),
            **({"pages": c.pages} if getattr(c, "pages", None) else {}),
        }
        for take in digest.takes
        for item in take.items
        for c in item.citations
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("story.html", render_story_html(digest))
        zf.writestr("sources.json", json.dumps(sources, indent=2))
    return buf.getvalue()
