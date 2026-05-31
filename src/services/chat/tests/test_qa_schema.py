"""QAScope / QAAnswer schema tests."""
from __future__ import annotations

from src.services.chat.schemas import QAScope, QAAnswer, TutorCitation


def test_qascope_defaults():
    s = QAScope(target_gap="the tradeoff itself")
    assert s.target_gap == "the tradeoff itself"
    assert s.assumed_known == []
    assert s.answer_form == "explanation"


def test_qascope_accepts_known_list_and_form():
    s = QAScope(
        target_gap="why bias and variance trade off",
        assumed_known=["definition of bias", "definition of variance"],
        answer_form="explanation",
    )
    assert "definition of bias" in s.assumed_known


def test_qaanswer_minimal_requires_text_and_scope():
    a = QAAnswer(text="The tradeoff is ...", scope=QAScope(target_gap="x"))
    assert a.text.startswith("The tradeoff")
    assert a.citations == []
    assert a.math_blocks == []
    assert a.grounding == {}


def test_qaanswer_carries_citations_and_grounding():
    a = QAAnswer(
        text="… [1].",
        scope=QAScope(target_gap="x"),
        citations=[TutorCitation(index=1, book_name="ISLP", quote="…")],
        grounding={"ok": True, "unsupported": [], "confidence": 0.9},
    )
    assert a.citations[0].index == 1
    assert a.grounding["ok"] is True
