"""Tests for qa.qa_bind — pure-code citation binder.

Contracts from the plan:
- Valid [[eid]] tokens → [n] (first-appearance numbering, shared across fields).
- Reused eid reuses its n.
- Invalid [[eid]] tokens → stripped, prose kept, grounding['unbound_markers'] incremented.
- Markdown heading markers stripped (## → text kept).
- Paragraph caps: intro≤1, deepening≤3, conclusion≤1; excess flagged in grounding['lints'].
- Corpus eid produces kind='corpus' citation.
"""
from __future__ import annotations

import src.services.chat.agents.qa as qa
from src.services.chat.research import Evidence
from src.services.chat.schemas import QAStoryDraft


# ---------------------------------------------------------------------------
# Provided contract tests (exact assertions from plan)
# ---------------------------------------------------------------------------

def test_bind_rewrites_valid_tokens_and_keeps_prose_on_invalid():
    e = Evidence(subject_id="qa", kind="wikipedia", text="t",
                 meta={"title": "Chebyshev's inequality", "url": "http://x"}, id="w1")
    draft = QAStoryDraft(intro="Named for Chebyshev [[w1]].",
                         deepening="Bound holds [[bad]]. Again [[w1]].", conclusion="Done.")
    ans = qa.qa_bind(draft, [e])
    assert "[1]" in ans.intro and ans.intro.count("[1]") == 1
    assert "[[w1]]" not in ans.deepening and "[1]" in ans.deepening   # reused n
    assert "[[bad]]" not in ans.deepening and ans.grounding["unbound_markers"] == 1
    assert "Bound holds" in ans.deepening   # prose kept
    assert "Bound holds." in ans.deepening  # no orphan space before period
    assert len(ans.citations) == 1 and ans.citations[0].kind == "wikipedia"
    assert ans.citations[0].title == "Chebyshev's inequality"   # verbatim from meta


def test_bind_strips_headings():
    ans = qa.qa_bind(QAStoryDraft(intro="## Overview\nHi", deepening="d", conclusion="c"), [])
    assert "##" not in ans.intro and "Hi" in ans.intro


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------

def test_bind_paragraph_cap_flags_in_lints_and_truncates():
    """deepening with 5 paragraphs → lints non-empty, and is truncated to ≤3."""
    deep = "\n\n".join([f"Para {i}." for i in range(5)])
    draft = QAStoryDraft(intro="Short.", deepening=deep, conclusion="End.")
    ans = qa.qa_bind(draft, [])
    # deepening must be truncated to at most 3 paragraphs
    para_count = len([p for p in ans.deepening.split("\n\n") if p.strip()])
    assert para_count <= 3
    # lints must name the field
    assert len(ans.grounding["lints"]) > 0
    assert any("deepening" in lint.lower() for lint in ans.grounding["lints"])


def test_bind_corpus_evidence_produces_corpus_citation():
    """A valid corpus eid produces a citation with kind='corpus'."""
    e = Evidence(
        subject_id="qa",
        kind="corpus",
        text="Some textbook content.",
        meta={
            "book_slug": "hansen",
            "book_name": "Econometrics",
            "authors": "Hansen",
            "year": 2022,
            "chapter": "ch03",
            "section_id": "3.2",
            "pages": "45–47",
            "chunk_id": "abc123",
        },
        id="corp1",
    )
    draft = QAStoryDraft(
        intro="Discussed in [[corp1]].",
        deepening="See textbook.",
        conclusion="Done.",
    )
    ans = qa.qa_bind(draft, [e])
    assert len(ans.citations) == 1
    assert ans.citations[0].kind == "corpus"
    assert "[1]" in ans.intro
