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


def test_modeid_includes_qa():
    from src.services.chat.schemas import ChatRequest
    req = ChatRequest(message="hi", mode="qa")
    assert req.mode == "qa"


def test_cost_table_has_qwen_and_gemini():
    from src.services.chat.cost import PRICE_PER_1M
    assert "qwen-plus" in PRICE_PER_1M
    assert "gemini-2.5-flash" in PRICE_PER_1M
    # generate-node estimate for nano stays cheap
    from src.services.chat.cost import usd_est
    assert usd_est("gpt-5.4-nano-2026-03-17", input_tokens=1800, output_tokens=250) < 0.001
