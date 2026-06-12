# src/services/chat/tests/test_facilitate_binder.py
from src.services.chat.agents.facilitate_story import (
    bind_concepts, strip_unbound_markers, statement_fidelity,
)
from src.services.chat.schemas.output import ConceptAnchor, ConceptProvenance


def _anchor(cid):
    return ConceptAnchor(id=cid, term=f"term-{cid}", kind="concept",
                         explanation="e", provenance=ConceptProvenance(book_slug="hansen"))


def test_strip_unbound_markers_removes_invented_keeps_text():
    body = "We rely on [[c1]] and also [[c9]] here."
    out = strip_unbound_markers(body, valid_ids={"c1"})
    assert "[[c1]]" in out and "[[c9]]" not in out and "here." in out


def test_bind_concepts_only_keeps_referenced_anchors():
    kept = bind_concepts([_anchor("c1"), _anchor("c2")], referenced_ids={"c1"})
    assert [a.id for a in kept] == ["c1"]


def test_statement_fidelity_passes_for_verbatim():
    src = "Theorem 7.4. The sample mean converges: $$\\bar X_n \\to \\mu$$ in probability."
    ok, score = statement_fidelity("The sample mean converges: $$\\bar X_n \\to \\mu$$", src)
    assert ok and score >= 0.8


def test_statement_fidelity_flags_fabricated():
    src = "Theorem 7.4. The sample mean converges in probability."
    ok, score = statement_fidelity("Every continuous function is differentiable", src)
    assert not ok and score < 0.5
