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


def test_retrieve_corpus_excludes_base_book(monkeypatch):
    captured = {}
    def _fake_hybrid(query, *, book_slugs=None, top_k=5, rerank=False, rerank_top_n=None, adjacent_sections=False):
        captured["book_slugs"] = book_slugs
        class S:
            text = "Distributions chapter text"
            book = "ross-probability"
            section = "5.1"
            score = 0.9
        return ([S()], None)
    monkeypatch.setattr(T, "hybrid_search", _fake_hybrid)

    out = T.make_retrieve_corpus(exclude_book="hansen-probability",
                                 all_slugs=["hansen-probability", "ross-probability"]).invoke(
        {"query": "distributions"})
    assert "hansen-probability" not in (captured["book_slugs"] or [])
    assert "ross-probability" in (captured["book_slugs"] or [])
    assert "Distributions" in out


def test_retrieve_peek_readonly(monkeypatch):
    def _fake_hybrid(query, *, book_slugs=None, top_k=5, rerank=False, rerank_top_n=None, adjacent_sections=False):
        class S:
            text = "peek"
            book = "b"
            section = "1"
            score = 0.5
        return ([S()], None)
    monkeypatch.setattr(T, "hybrid_search", _fake_hybrid)
    out = T.make_retrieve_peek(all_slugs=["b"]).invoke({"query": "x"})
    assert "peek" in out
