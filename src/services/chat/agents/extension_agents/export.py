"""Build a self-contained styled-HTML ZIP for an ExtensionDigest.

Chinese-wall: schemas only."""
from __future__ import annotations

import html as _html
import io
import json
import zipfile

_KATEX = ("https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css")
_KATEX_JS = ("https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js")
_AUTO = ("https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js")

_CSS = """
body{font-family:Georgia,serif;max-width:46rem;margin:3rem auto;padding:0 1rem;color:#1a1a1a;line-height:1.6}
h1{font-size:1.8rem;border-bottom:2px solid #333;padding-bottom:.4rem}
h2{font-size:1.3rem;margin-top:2.2rem;color:#222}
.fn{font-size:.85rem;color:#444;border-left:3px solid #bbb;padding-left:.8rem;margin:.4rem 0}
.fn .src{color:#888;font-style:italic}
sup{color:#0a58ca}
.gaps{margin-top:3rem;color:#a33;font-size:.9rem}
"""


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
    parts.append(
        f'<script defer src="{_KATEX_JS}"></script>'
        f'<script defer src="{_AUTO}" '
        "onload=\"renderMathInElement(document.body,{delimiters:["
        "{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}]})\">"
        "</script>"
    )
    parts.append("</body></html>")
    return "".join(parts)


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
