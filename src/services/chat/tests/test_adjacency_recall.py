"""Tests for adjacent-section expansion + author-cap recall upgrades."""
from src.services.chat.retrievers import density as den
from src.services.chat.agents import deep_tutor as d


class _Rec:
    def __init__(self, pid, payload):
        self.id = pid
        self.payload = payload


def _rec(pid, section_id, page_from):
    return _Rec(pid, {"section_id": section_id, "page_from": page_from, "book_slug": "b", "text": "x"})


def test_parent_section():
    assert den._parent_section("2.2.1") == "2.2"
    assert den._parent_section("3") == "3"
    assert den._parent_section("") == ""


def test_neighbor_chunks_graceful_on_error(monkeypatch):
    class _Boom:
        def scroll(self, *a, **k):
            raise RuntimeError("boom")
    monkeypatch.setattr(den, "client", lambda: _Boom())
    out = den._fetch_neighbor_chunks("b", "2.2.2", 10, ["c"], set())
    assert out == []


def test_neighbor_chunks_none_page():
    assert den._fetch_neighbor_chunks("b", "2.2.2", None, ["c"], set()) == []


def test_neighbor_chunks_picks_nearest_siblings(monkeypatch):
    # selected = section 2.2.2 at page 10. siblings 2.2.1 (p8) before, 2.2.3 (p12) after.
    # 2.3.1 (p13) is NOT a sibling (different parent); 9.9 far away.
    recs = [
        _rec("a", "2.2.1", 8),
        _rec("b", "2.2.2", 10),   # same section as selected → excluded
        _rec("c", "2.2.3", 12),
        _rec("d", "2.3.1", 13),   # different parent
    ]
    class _C:
        def scroll(self, *a, **k):
            return (recs, None)
    monkeypatch.setattr(den, "client", lambda: _C())
    out = den._fetch_neighbor_chunks("b", "2.2.2", 10, ["c"], set())
    ids = {p.id for p in out}
    assert ids == {"a", "c"}            # nearest sibling before + after
    assert "b" not in ids and "d" not in ids


def test_neighbor_chunks_dedups_seen(monkeypatch):
    recs = [_rec("a", "2.2.1", 8), _rec("c", "2.2.3", 12)]
    class _C:
        def scroll(self, *a, **k):
            return (recs, None)
    monkeypatch.setattr(den, "client", lambda: _C())
    seen = {"a"}
    out = den._fetch_neighbor_chunks("b", "2.2.2", 10, ["c"], seen)
    assert {p.id for p in out} == {"c"}   # "a" already seen


def test_author_cap_raised_to_6():
    assert d._DIVERSITY_MAX >= 6
    mode, cap = d._resolve_diversity("auto")
    assert mode == "auto" and cap >= 6


def test_resolve_diversity_fixed_6_not_clamped():
    # was the bug: min(6, 5) == 5 clamped the request to 5
    mode, cap = d._resolve_diversity(6)
    assert mode == "fixed" and cap == 6


# --- author-cap honored end-to-end (set N -> get N up to corpus limit) -------

class _Src:
    """Minimal Source-like for density/rerank tests."""
    def __init__(self, book, section, author, page_from, score=1.0, chunk="x", chunkId=None):
        self.book = book
        self.section = section
        self.authors = author
        self.authors_short = author
        self.year = 2000
        self.page_from = page_from
        self.score = score
        self.chunk = chunk
        self.excerpt = chunk
        self.chunkId = chunkId or f"{book}:{section}:{page_from}"


def _identity_reranker(monkeypatch):
    """Reranker that returns the first top_n by incoming order (score-blind)."""
    class _RR:
        def rerank(self, query, sources, top_n):
            return list(sources)[:top_n]
    monkeypatch.setattr(d, "get_reranker", lambda: _RR())


def test_density_select_scales_sections_to_target(monkeypatch):
    _identity_reranker(monkeypatch)
    monkeypatch.setattr(d, "_NEIGHBOR_EXPAND", False)
    monkeypatch.setattr(d, "collections_for_books", lambda slugs: {"c": slugs})
    monkeypatch.setattr(d, "_fetch_section_chunks", lambda *a, **k: [])
    monkeypatch.setattr(d, "_source_to_pseudo_point", lambda s: s)
    monkeypatch.setattr(d, "_point_to_source", lambda p, rank: p)
    # 6 distinct authors, one section each, all contain the concept "x".
    cands = [_Src("b%d" % i, "1.%d" % i, "auth%d" % i, 10 + i) for i in range(6)]
    sources, _ = d._density_select(
        "q", ["x"], cands, book_slugs=["b0"], top_sections=4, final_top_n=8, target_authors=6,
    )
    authors = {s.authors for s in sources}
    assert len(authors) == 6   # was capped at 4 by top_sections before the fix


def test_density_select_corpus_limit_honest(monkeypatch):
    _identity_reranker(monkeypatch)
    monkeypatch.setattr(d, "_NEIGHBOR_EXPAND", False)
    monkeypatch.setattr(d, "collections_for_books", lambda slugs: {"c": slugs})
    monkeypatch.setattr(d, "_fetch_section_chunks", lambda *a, **k: [])
    monkeypatch.setattr(d, "_source_to_pseudo_point", lambda s: s)
    monkeypatch.setattr(d, "_point_to_source", lambda p, rank: p)
    cands = [_Src("b%d" % i, "1.%d" % i, "auth%d" % i, 10 + i) for i in range(3)]
    sources, _ = d._density_select(
        "q", ["x"], cands, book_slugs=["b0"], top_sections=4, final_top_n=8, target_authors=6,
    )
    assert len({s.authors for s in sources}) == 3   # only 3 authors exist -> no crash, no padding
