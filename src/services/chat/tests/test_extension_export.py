import io
import json
import zipfile
from src.services.chat.agents.extension_agents.export import build_export_zip
from src.services.chat.schemas import ExtensionDigest, ExtensionPoint, ExtensionFootnote
from src.services.chat.schemas import StoryDigest, Take, CuriosityItem, StoryCitation


def _digest():
    return ExtensionDigest(book="hansen-probability", chapter="ch07",
        points=[ExtensionPoint(title="LLN", curated_text="The mean converges.",
            footnotes=[ExtensionFootnote(marker="1", body="$\\bar X\\to\\mu$",
                                         source="ross §5.1", kind="corpus")])],
        unfilled_gaps=[])


def test_zip_contains_html_and_sources():
    blob = build_export_zip(_digest())
    zf = zipfile.ZipFile(io.BytesIO(blob))
    names = set(zf.namelist())
    assert "extension.html" in names
    assert "sources.json" in names
    html = zf.read("extension.html").decode()
    assert "<html" in html.lower()
    assert "LLN" in html
    assert "katex" in html.lower()
    assert "The mean converges" in html
    sources = json.loads(zf.read("sources.json"))
    assert sources[0]["source"] == "ross §5.1"


def test_html_is_self_contained():
    html = zipfile.ZipFile(io.BytesIO(build_export_zip(_digest()))).read("extension.html").decode()
    assert "<style" in html.lower()


def test_export_endpoint_returns_zip():
    from fastapi.testclient import TestClient
    from src.services.chat.api import app
    client = TestClient(app)
    payload = {"book": "b", "chapter": "ch01",
               "points": [{"title": "t", "curated_text": "x", "footnotes": []}],
               "unfilled_gaps": []}
    r = client.post("/api/export", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert len(r.content) > 0


def test_export_story_digest_html_structure():
    from src.services.chat.agents.extension_agents.export import render_story_html
    d = StoryDigest(book="hansen-probability", chapter="ch07 · 7.4–7.5", takes=[
        Take(heading="Chebyshev", story="Opens with $\\mu$…", items=[
            CuriosityItem(subject="Why $\\delta^{-2}$", body="Because…",
                          citations=[StoryCitation(kind="wikipedia", label="Wikipedia: X",
                                                   title="X", url="https://en.wikipedia.org/wiki/X")])])])
    html = render_story_html(d)
    assert "Chebyshev" in html and "katex" in html.lower()
    assert "footnote" in html.lower()                      # curiosity as footnotes
    assert 'href="https://en.wikipedia.org/wiki/X"' in html
    assert "text-align: justify" in html or "text-align:justify" in html


def test_export_filename_sanitized():
    from src.services.chat.agents.extension_agents.export import zip_filename
    assert zip_filename("hansen-probability", "ch07 · 7.4–7.5") == \
        "hansen-probability-ch07-7.4-7.5-extended.zip"


def test_export_endpoint_story_digest_returns_zip():
    """Route-level: StoryDigest payload (has 'takes') triggers v2 path."""
    from fastapi.testclient import TestClient
    from src.services.chat.api import app
    client = TestClient(app)
    payload = {
        "book": "hansen-probability",
        "chapter": "ch07 · 7.4–7.5",
        "takes": [
            {
                "heading": "Chebyshev",
                "story": "The law states…",
                "items": [
                    {
                        "subject": "Why tail bounds",
                        "body": "Because variance is finite.",
                        "citations": [
                            {"kind": "wikipedia", "label": "Wikipedia: Chebyshev",
                             "title": "Chebyshev's inequality",
                             "url": "https://en.wikipedia.org/wiki/Chebyshev%27s_inequality"},
                        ],
                    }
                ],
            }
        ],
        "unfilled_subjects": [],
    }
    r = client.post("/api/export", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert len(r.content) > 0
    # filename must be sanitized
    disp = r.headers.get("content-disposition", "")
    assert "hansen-probability-ch07-7.4-7.5-extended.zip" in disp


# ---------------------------------------------------------------------------
# HIGH: 400 on malformed body / 422 on invalid payload
# ---------------------------------------------------------------------------

def test_export_malformed_body_returns_400():
    """Non-JSON body → 400 invalid JSON body."""
    from fastapi.testclient import TestClient
    from src.services.chat.api import app
    client = TestClient(app)
    r = client.post(
        "/api/export",
        content=b"this is not json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert "invalid JSON body" in r.text


def test_export_invalid_story_digest_returns_422():
    """Payload with 'takes' key but wrong type → 422 with validation errors."""
    from fastapi.testclient import TestClient
    from src.services.chat.api import app
    client = TestClient(app)
    # 'takes' present but nonsense value — will fail StoryDigest validation
    r = client.post("/api/export", json={"takes": "nonsense"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and len(detail) > 0


# ---------------------------------------------------------------------------
# MEDIUM: URL scheme allowlist — javascript: must not produce <a href>
# ---------------------------------------------------------------------------

def test_render_story_html_javascript_url_no_anchor():
    """Citation with javascript: url must not produce an <a href>, label still present."""
    from src.services.chat.agents.extension_agents.export import render_story_html
    d = StoryDigest(
        book="b", chapter="ch01",
        takes=[
            Take(
                heading="H",
                story="S",
                items=[
                    CuriosityItem(
                        subject="Sub",
                        body="Body text.",
                        citations=[
                            StoryCitation(
                                kind="wikipedia",
                                label="Malicious link",
                                title="X",
                                url="javascript:alert(1)",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    html = render_story_html(d)
    assert "<a" not in html or "javascript:" not in html  # no anchor with js: url
    # More precise: no <a element at all for this citation
    assert "javascript:" not in html
    assert "Malicious link" in html  # label still present as plain text


# ---------------------------------------------------------------------------
# LOW: Escape-invariant — XSS payloads in heading/story/subject/body
# ---------------------------------------------------------------------------

def test_render_story_html_escapes_xss_payloads():
    """<script> tags in heading/story/subject/body must be HTML-escaped."""
    from src.services.chat.agents.extension_agents.export import render_story_html
    xss = "<script>alert(1)</script>"
    d = StoryDigest(
        book=xss, chapter=xss,
        takes=[
            Take(
                heading=xss,
                story=xss,
                items=[
                    CuriosityItem(
                        subject=xss,
                        body=xss,
                        citations=[
                            StoryCitation(kind="corpus", label=xss, title="X")
                        ],
                    )
                ],
            )
        ],
    )
    html = render_story_html(d)
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html
