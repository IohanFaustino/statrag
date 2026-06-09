import src.services.chat.agents.extension_agents.tools as T


def test_wikipedia_lookup_returns_extract(monkeypatch):
    class _Resp:
        status_code = 200
        def json(self):
            return {"title": "Probability distribution",
                    "extract": "A probability distribution is a mathematical function...",
                    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Probability_distribution"}}}
        def raise_for_status(self): pass

    def _fake_get(url, *a, **k):
        assert "rest_v1/page/summary" in url
        return _Resp()

    monkeypatch.setattr(T.httpx, "get", _fake_get)
    out = T.wikipedia_lookup.invoke({"query": "probability distribution"})
    assert "mathematical function" in out
    assert "en.wikipedia.org/wiki/Probability_distribution" in out


def test_wikipedia_lookup_handles_missing(monkeypatch):
    class _Resp:
        status_code = 404
        def json(self): return {}
        def raise_for_status(self): pass
    monkeypatch.setattr(T.httpx, "get", lambda url, *a, **k: _Resp())
    out = T.wikipedia_lookup.invoke({"query": "zzznotreal"})
    assert "no wikipedia" in out.lower()
