import io
import json
import zipfile
from src.services.chat.agents.extension_agents.export import build_export_zip
from src.services.chat.schemas import ExtensionDigest, ExtensionPoint, ExtensionFootnote


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
