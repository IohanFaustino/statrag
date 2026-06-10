"""Citation binder: bullets cite only via evidence_ids; fields copied verbatim."""
from src.services.chat.agents.extension_agents.binder import BulletDraft, bind_citations
from src.services.chat.agents.extension_agents.research import Evidence


def _ev_corpus(eid="e1", sid="s1"):
    return Evidence(id=eid, subject_id=sid, kind="corpus", text="…",
                    meta={"book_slug": "moss", "book_name": "Probability",
                          "authors": "Marcus Moss", "year": 2020, "chapter": "ch06",
                          "section_id": "6.5.2", "pages": "142–144", "chunk_id": "c-1"})


def _ev_wiki(eid="e2", sid="s1"):
    return Evidence(id=eid, subject_id=sid, kind="wikipedia", text="…",
                    meta={"title": "Chebyshev's inequality",
                          "url": "https://en.wikipedia.org/wiki/Chebyshev%27s_inequality"})


def test_binder_builds_citations_verbatim_from_evidence():
    bullets = [BulletDraft(take_idx=0, subject="Why δ⁻²", body="Because…",
                           evidence_ids=["e1", "e2"])]
    items, dropped = bind_citations(bullets, [_ev_corpus(), _ev_wiki()])
    cits = items[0][1].citations
    corpus = next(c for c in cits if c.kind == "corpus")
    wiki = next(c for c in cits if c.kind == "wikipedia")
    assert corpus.book_name == "Probability" and corpus.pages == "142–144"
    assert corpus.section_id == "6.5.2" and corpus.chunk_id == "c-1"
    assert "Moss" in corpus.label and "6.5.2" in corpus.label
    assert wiki.url.endswith("Chebyshev%27s_inequality") and wiki.label.startswith("Wikipedia:")
    assert dropped == []


def test_binder_drops_bullet_with_no_valid_ids():
    bullets = [BulletDraft(take_idx=0, subject="Ghost", body="…",
                           evidence_ids=["nope"])]
    items, dropped = bind_citations(bullets, [_ev_corpus()])
    assert items == [] and dropped == ["Ghost"]


def test_binder_ignores_invalid_ids_but_keeps_valid_ones():
    bullets = [BulletDraft(take_idx=1, subject="Half", body="…",
                           evidence_ids=["e1", "invented"])]
    items, dropped = bind_citations(bullets, [_ev_corpus()])
    assert len(items[0][1].citations) == 1 and dropped == []


def test_binder_property_no_field_outside_evidence():
    """Every populated citation field value must literally appear in some evidence meta."""
    evs = [_ev_corpus(), _ev_wiki()]
    bullets = [BulletDraft(take_idx=0, subject="x", body="…", evidence_ids=["e1", "e2"])]
    items, _ = bind_citations(bullets, evs)
    allowed = set()
    for e in evs:
        allowed |= {str(v) for v in e.meta.values() if v is not None}
    for _, item in items:
        for c in item.citations:
            for f in ("book_slug", "book_name", "authors", "chapter",
                      "section_id", "pages", "title", "url", "chunk_id"):
                v = getattr(c, f)
                if v is not None:
                    assert str(v) in allowed, f"{f}={v!r} not from evidence"
