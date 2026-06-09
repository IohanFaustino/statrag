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
            chunk = "Distributions chapter text"
            excerpt = "Distributions excerpt"
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
            chunk = "peek"
            excerpt = "peek excerpt"
            book = "b"
            section = "1"
            score = 0.5
        return ([S()], None)
    monkeypatch.setattr(T, "hybrid_search", _fake_hybrid)
    out = T.make_retrieve_peek(all_slugs=["b"]).invoke({"query": "x"})
    assert "peek" in out


def test_wikipedia_disambiguation_fallback(monkeypatch):
    """When direct title lookup returns 404, fall back to search API."""
    call_log = []

    class _Resp404:
        status_code = 404
        def json(self): return {}

    class _SearchResp:
        status_code = 200
        def json(self):
            return {"query": {"search": [{"title": "Law of large numbers"}]}}

    class _SummaryResp:
        status_code = 200
        def json(self):
            return {
                "extract": "The law of large numbers is a theorem...",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Law_of_large_numbers"}},
            }

    def _fake_get(url, *a, **k):
        call_log.append(url)
        if "rest_v1/page/summary" in url and "Law_of_large_numbers" in url:
            return _SummaryResp()
        if "api.php" in url:
            return _SearchResp()
        return _Resp404()

    monkeypatch.setattr(T.httpx, "get", _fake_get)
    out = T.wikipedia_lookup.invoke({"query": "lln theorem"})
    assert "law of large numbers" in out.lower()
    # Verify the search API was called (disambiguation path used)
    assert any("api.php" in u for u in call_log)


def test_retrieve_corpus_top_k_is_10(monkeypatch):
    captured = {}
    def _fake_hybrid(query, *, book_slugs=None, top_k=5, rerank=False, **kw):
        captured["top_k"] = top_k
        return ([], None)
    monkeypatch.setattr(T, "hybrid_search", _fake_hybrid)
    T.make_retrieve_corpus(exclude_book="b", all_slugs=["b", "c"]).invoke({"query": "x"})
    assert captured["top_k"] == 10


def test_retrieve_corpus_dedup_seen_ids(monkeypatch):
    seen: set[str] = set()
    class _S:
        chunk = "text"
        excerpt = "text"
        book = "ross"
        section = "5.1"
        chunk_id = "abc123"
        score = 0.9
    def _fake_hybrid(*a, **k):
        return ([_S()], None)
    monkeypatch.setattr(T, "hybrid_search", _fake_hybrid)

    corpus = T.make_retrieve_corpus(exclude_book="b", all_slugs=["b", "ross"], seen_ids=seen)
    # First call: abc123 is new → returns result
    out1 = corpus.invoke({"query": "x"})
    assert "text" in out1
    assert "abc123" in seen
    # Second call: abc123 already seen → deduped → no results
    out2 = corpus.invoke({"query": "x"})
    assert "no results" in out2
