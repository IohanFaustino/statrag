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

def _sanitize_slug(s: str) -> str:
    """Sanitize a book slug or chapter label to ``[a-z0-9._-]`` only.

    Replacements (applied in order):
    - Unicode middle-dot ``·`` (U+00B7) and en-dash ``–`` (U+2013) and
      em-dash ``—`` (U+2014) → ``-``
    - Any remaining whitespace → ``-``
    - Any character outside ``[a-z0-9._-]`` → ``-``
    - Two-or-more consecutive ``-`` → single ``-``
    - Leading/trailing ``-`` stripped
    """
    s = s.replace("·", "-").replace("–", "-").replace("—", "-")
    s = s.replace(" ", "-")
    s = re.sub(r"[^a-z0-9._\-]", "-", s.lower())
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


def zip_filename(book: str, chapter: str) -> str:
    """Return a sanitized ZIP filename for a digest.

    Both *book* and *chapter* are passed through :func:`_sanitize_slug` so the
    result contains only ``[a-z0-9._-]``.

    Example::

        zip_filename("hansen-probability", "ch07 · 7.4–7.5")
        # → "hansen-probability-ch07-7.4-7.5-extended.zip"
    """
    b = _sanitize_slug(book)
    ch = _sanitize_slug(chapter)
    return f"{b}-{ch}-extended.zip"


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
# Markdown renderers (mirror web/src/lib/exportMarkdown.ts; content fields are
# already markdown text so they pass through verbatim). One per digest type;
# each ZIP ships a .md beside its .html.
# ---------------------------------------------------------------------------

def _fmt_tutor_citation(c) -> str:
    parts = [p for p in (
        getattr(c, "authors_short", ""), str(getattr(c, "year", "") or ""),
        getattr(c, "book_name", ""), getattr(c, "chapter", ""), getattr(c, "section", ""),
    ) if p]
    pf, pt = getattr(c, "page_from", 0), getattr(c, "page_to", 0)
    if pf:
        parts.append(f"pp. {pf}–{pt}" if pt and pt != pf else f"p. {pf}")
    return " · ".join(parts)


def _fmt_label_citation(i, c) -> str:
    prefix = "🌐 " if getattr(c, "kind", "corpus") == "wikipedia" else ""
    tail = f" · {c.url}" if getattr(c, "url", None) else ""
    return f"{prefix}[{i}] {c.label}{tail}"


def _md_math(lines: list[str], math_blocks) -> None:
    if math_blocks:
        lines += ["---", "", "## Math", ""]
        for tex in math_blocks:
            lines += ["$$", tex, "$$", ""]


def render_extension_md(digest) -> str:
    lines = [f"# {digest.book} · {digest.chapter} — Extended", ""]
    for pt in digest.points:
        lines += [f"## {pt.title}", "", pt.curated_text, ""]
        for fn in pt.footnotes:
            lines.append(f"> [{fn.marker}] {fn.body} — _{fn.source} · {fn.kind}_")
        if pt.footnotes:
            lines.append("")
    if digest.unfilled_gaps:
        lines += ["---", "", f"**Unfilled gaps:** {', '.join(digest.unfilled_gaps)}", ""]
    return "\n".join(lines)


def render_story_md(digest) -> str:
    lines = [f"# {digest.book} · {digest.chapter} — Extended", ""]
    for i, take in enumerate(digest.takes, 1):
        lines += [f"## {i}. {take.heading}", "", take.story, ""]
        for item in take.items:
            cits = " · ".join(c.label for c in item.citations)
            suffix = f" _[{cits}]_" if cits else ""
            lines.append(f"- **{item.subject}** — {item.body}{suffix}")
        if take.items:
            lines.append("")
    if getattr(digest, "unfilled_subjects", None):
        lines += ["---", "", f"**Unfilled subjects:** {', '.join(digest.unfilled_subjects)}", ""]
    return "\n".join(lines)


def render_tutor_md(data) -> str:
    lines = [f"# {getattr(data, 'title', None) or 'Tutor Answer'}", "", getattr(data, "text", ""), ""]
    _md_math(lines, getattr(data, "math_blocks", []) or [])
    citations = getattr(data, "citations", []) or []
    if citations:
        lines += ["---", "", "## References", ""]
        lines += [f"[{c.index}] {_fmt_tutor_citation(c)}" for c in citations]
        lines.append("")
    return "\n".join(lines)


def render_qa_md(data) -> str:
    lines = ["# Q&A Answer", ""]
    scope = getattr(data, "scope", None)
    if scope and getattr(scope, "target_gap", None):
        lines += [f"**Question:** {scope.target_gap}", ""]
    lines += [data.intro, "", data.deepening, "", data.conclusion, ""]
    _md_math(lines, getattr(data, "math_blocks", []) or [])
    citations = getattr(data, "citations", []) or []
    if citations:
        lines += ["---", "", "## References", ""]
        lines += [_fmt_label_citation(i, c) for i, c in enumerate(citations, 1)]
        lines.append("")
    return "\n".join(lines)


def render_chapter_md(data) -> str:
    title = "Facilitate Digest" if getattr(data, "mode", "") == "facilitate" else "Resume Digest"
    lines = [f"# {title}", "", f"**Book:** {data.scope.book_slug}",
             f"**Chapter:** {data.scope.chapter_id}", ""]
    if getattr(data, "intro", ""):
        lines += [data.intro, ""]
    for block in getattr(data, "blocks", []) or []:
        lines += [f"## {block.h2_path}", ""]
        if block.page_from > 0:
            pg = f"pp. {block.page_from}–{block.page_to}" if block.page_to > block.page_from else f"p. {block.page_from}"
            lines += [f"*{pg}*", ""]
        lines += [block.body, ""]
    _md_math(lines, getattr(data, "math_blocks", []) or [])
    if getattr(data, "outro", ""):
        lines += [data.outro, ""]
    citations = getattr(data, "citations", []) or []
    if citations:
        lines += ["---", "", "## References", ""]
        lines += [f"[{c.index}] {_fmt_tutor_citation(c)}" for c in citations]
        lines.append("")
    return "\n".join(lines)


def render_facilitate_md(data) -> str:
    scope = getattr(data, "scope", None)
    section = ", ".join(scope.requested_subtopics) if scope and scope.requested_subtopics else "Unknown"
    lines = ["# Facilitate Story", "", f"**Section:** {section}", ""]
    if getattr(data, "hook", ""):
        lines += [data.hook, ""]
    for m in getattr(data, "movements", []) or []:
        if getattr(m, "formal", None):
            f = m.formal
            quoted = "> " + f.statement.replace("\n", "\n> ")
            lines += [f"## {f.kind.upper()}", "", quoted, "", f.explanation, ""]
        elif getattr(m, "prose", None):
            lines += [m.prose, ""]
    if getattr(data, "takeaway", ""):
        lines += ["---", "", data.takeaway, ""]
    citations = getattr(data, "citations", []) or []
    if citations:
        lines += ["---", "", "## References", ""]
        lines += [_fmt_label_citation(i, c) for i, c in enumerate(citations, 1)]
        lines.append("")
    return "\n".join(lines)


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
        zf.writestr("extension.md", render_extension_md(digest))
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
        zf.writestr("story.md", render_story_md(digest))
        zf.writestr("sources.json", json.dumps(sources, indent=2))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# TutorAnswer renderer + ZIP builder
# ---------------------------------------------------------------------------

def render_tutor_html(data) -> str:
    """Return self-contained HTML for a TutorAnswer."""
    title = getattr(data, "title", "Tutor Answer")
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        f"<title>{_html.escape(title)}</title>",
        f'<link rel="stylesheet" href="{_KATEX}">',
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{_html.escape(title)}</h1>",
    ]
    # Body text with ## headings
    text = getattr(data, "text", "")
    if text:
        # Convert ## headings to HTML h2
        html_body = _html.escape(text).replace("\n## ", "</p><h2>").replace("\n", "<br>")
        parts.append(f'<div class="tutor-body">{html_body}</div>')
    # Math blocks
    math_blocks = getattr(data, "math_blocks", []) or []
    if math_blocks:
        parts.append("<h2>Math</h2>")
        for tex in math_blocks:
            parts.append(f"<p>$$${_html.escape(tex)}$$</p>")
    # Citations
    citations = getattr(data, "citations", []) or []
    if citations:
        parts.append("<h2>References</h2><ol>")
        for c in citations:
            who = _html.escape(f"{c.authors_short} {c.year}".strip())
            loc = _html.escape(f"{c.book_name} · {c.chapter} · {c.section}".strip(" ·"))
            pg = f"p. {c.page_from}" if c.page_from else ""
            parts.append(f"<li>[{c.index}] {who} — {loc} {pg}</li>")
        parts.append("</ol>")
    parts.append(_KATEX_SCRIPT)
    parts.append("</body></html>")
    return "".join(parts)


def build_tutor_export_zip(data) -> bytes:
    """Return ZIP bytes for a TutorAnswer: tutor.html + sources.json."""
    sources = [
        {
            "index": c.index,
            "authors": c.authors_short,
            "year": c.year,
            "book": c.book_name,
            "chapter": c.chapter,
            "section": c.section,
            "pages": f"{c.page_from}-{c.page_to}" if c.page_to else str(c.page_from),
        }
        for c in getattr(data, "citations", []) or []
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("tutor.html", render_tutor_html(data))
        zf.writestr("tutor.md", render_tutor_md(data))
        zf.writestr("sources.json", json.dumps(sources, indent=2))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Q&A (QAStoryAnswer) renderer + ZIP builder
# ---------------------------------------------------------------------------

def render_qa_html(data) -> str:
    """Return self-contained HTML for a QAStoryAnswer."""
    scope = getattr(data, "scope", None)
    target = scope.target_gap if scope else "Q&A Answer"
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        f"<title>{_html.escape(target)}</title>",
        f'<link rel="stylesheet" href="{_KATEX}">',
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{_html.escape(target)}</h1>",
    ]
    # Three-act structure
    parts.append(f'<div class="qa-intro"><p>{_html.escape(data.intro)}</p></div>')
    parts.append(f'<div class="qa-deepening"><p>{_html.escape(data.deepening)}</p></div>')
    parts.append(f'<div class="qa-conclusion"><p>{_html.escape(data.conclusion)}</p></div>')
    # Math blocks
    math_blocks = getattr(data, "math_blocks", []) or []
    if math_blocks:
        parts.append("<h2>Math</h2>")
        for tex in math_blocks:
            parts.append(f"<p>$$${_html.escape(tex)}$$</p>")
    # Citations
    citations = getattr(data, "citations", []) or []
    if citations:
        parts.append("<h2>References</h2><ol>")
        for i, c in enumerate(citations, 1):
            label = _html.escape(c.label)
            kind = getattr(c, "kind", "corpus")
            prefix = "🌐 " if kind == "wikipedia" else ""
            parts.append(f"<li>{prefix}[{i}] {label}</li>")
        parts.append("</ol>")
    parts.append(_KATEX_SCRIPT)
    parts.append("</body></html>")
    return "".join(parts)


def build_qa_export_zip(data) -> bytes:
    """Return ZIP bytes for a QAStoryAnswer: qa.html + sources.json."""
    sources = [
        {
            "index": i + 1,
            "label": c.label,
            "kind": getattr(c, "kind", "corpus"),
            **({"url": c.url} if getattr(c, "url", None) else {}),
        }
        for i, c in enumerate(getattr(data, "citations", []) or [])
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("qa.html", render_qa_html(data))
        zf.writestr("qa.md", render_qa_md(data))
        zf.writestr("sources.json", json.dumps(sources, indent=2))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# ChapterDigest renderer + ZIP builder
# ---------------------------------------------------------------------------

def render_chapter_html(data) -> str:
    """Return self-contained HTML for a ChapterDigest (resume/facilitate)."""
    mode = getattr(data, "mode", "chapter")
    title = "Facilitate Digest" if mode == "facilitate" else "Resume Digest"
    scope = getattr(data, "scope", None)
    book = scope.book_slug if scope else "Unknown"
    chapter = scope.chapter_id if scope else "Unknown"
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        f"<title>{_html.escape(title)}</title>",
        f'<link rel="stylesheet" href="{_KATEX}">',
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{_html.escape(title)}</h1>",
        f"<p><strong>Book:</strong> {_html.escape(book)}<br>",
        f"<strong>Chapter:</strong> {_html.escape(chapter)}</p>",
    ]
    # Intro
    intro = getattr(data, "intro", "")
    if intro:
        parts.append(f'<div class="chapter-intro"><p>{_html.escape(intro)}</p></div>')
    # Blocks
    blocks = getattr(data, "blocks", []) or []
    for block in blocks:
        h2 = _html.escape(block.h2_path)
        parts.append(f"<h2>{h2}</h2>")
        if block.page_from:
            pg = f"pp. {block.page_from}-{block.page_to}" if block.page_to else f"p. {block.page_from}"
            parts.append(f"<p><em>{_html.escape(pg)}</em></p>")
        parts.append(f'<div class="block-body"><p>{_html.escape(block.body)}</p></div>')
    # Math blocks
    math_blocks = getattr(data, "math_blocks", []) or []
    if math_blocks:
        parts.append("<h2>Math</h2>")
        for tex in math_blocks:
            parts.append(f"<p>$$${_html.escape(tex)}$$</p>")
    # Outro
    outro = getattr(data, "outro", "")
    if outro:
        parts.append(f'<div class="chapter-outro"><p>{_html.escape(outro)}</p></div>')
    # Citations
    citations = getattr(data, "citations", []) or []
    if citations:
        parts.append("<h2>References</h2><ol>")
        for c in citations:
            who = _html.escape(f"{c.authors_short} {c.year}".strip())
            loc = _html.escape(f"{c.book_name} · {c.chapter}".strip(" ·"))
            parts.append(f"<li>[{c.index}] {who} — {loc}</li>")
        parts.append("</ol>")
    parts.append(_KATEX_SCRIPT)
    parts.append("</body></html>")
    return "".join(parts)


def build_chapter_export_zip(data) -> bytes:
    """Return ZIP bytes for a ChapterDigest: chapter.html + sources.json."""
    sources = [
        {
            "index": c.index,
            "authors": c.authors_short,
            "year": c.year,
            "book": c.book_name,
            "chapter": c.chapter,
            "section": c.section,
            "pages": f"{c.page_from}-{c.page_to}" if c.page_to else str(c.page_from),
        }
        for c in getattr(data, "citations", []) or []
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("chapter.html", render_chapter_html(data))
        zf.writestr("chapter.md", render_chapter_md(data))
        zf.writestr("sources.json", json.dumps(sources, indent=2))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# FacilitateStory renderer + ZIP builder
# ---------------------------------------------------------------------------

def render_facilitate_html(data) -> str:
    """Return self-contained HTML for a FacilitateStory."""
    scope = getattr(data, "scope", None)
    section = scope.requested_subtopics if scope else ["Unknown"]
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        "<title>Facilitate Story</title>",
        f'<link rel="stylesheet" href="{_KATEX}">',
        f"<style>{_CSS}</style></head><body>",
        "<h1>Facilitate Story</h1>",
        f"<p><strong>Section:</strong> {_html.escape(', '.join(section))}</p>",
    ]
    # Hook
    hook = getattr(data, "hook", "")
    if hook:
        parts.append(f'<div class="story-hook"><p><em>{_html.escape(hook)}</em></p></div>')
    # Movements
    movements = getattr(data, "movements", []) or []
    for m in movements:
        if getattr(m, "formal", None):
            f = m.formal
            parts.append(f"<h2>{_html.escape(f.kind.upper())}</h2>")
            parts.append(f'<blockquote>{_html.escape(f.statement)}</blockquote>')
            parts.append(f'<p>{_html.escape(f.explanation)}</p>')
        elif getattr(m, "prose", None):
            parts.append(f'<p>{_html.escape(m.prose)}</p>')
    # Takeaway
    takeaway = getattr(data, "takeaway", "")
    if takeaway:
        parts.append("<h2>Takeaway</h2>")
        parts.append(f'<p>{_html.escape(takeaway)}</p>')
    # Citations
    citations = getattr(data, "citations", []) or []
    if citations:
        parts.append("<h2>References</h2><ol>")
        for i, c in enumerate(citations, 1):
            label = _html.escape(c.label)
            kind = getattr(c, "kind", "corpus")
            prefix = "🌐 " if kind == "wikipedia" else ""
            parts.append(f"<li>{prefix}[{i}] {label}</li>")
        parts.append("</ol>")
    parts.append(_KATEX_SCRIPT)
    parts.append("</body></html>")
    return "".join(parts)


def build_facilitate_export_zip(data) -> bytes:
    """Return ZIP bytes for a FacilitateStory: facilitate.html + sources.json."""
    sources = [
        {
            "index": i + 1,
            "label": c.label,
            "kind": getattr(c, "kind", "corpus"),
            **({"url": c.url} if getattr(c, "url", None) else {}),
        }
        for i, c in enumerate(getattr(data, "citations", []) or [])
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("facilitate.html", render_facilitate_html(data))
        zf.writestr("facilitate.md", render_facilitate_md(data))
        zf.writestr("sources.json", json.dumps(sources, indent=2))
    return buf.getvalue()
