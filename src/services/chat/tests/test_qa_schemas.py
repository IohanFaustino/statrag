"""QA per-call output schemas exist and have the expected shape."""
from __future__ import annotations


def test_qa_generate_out_shape():
    from src.services.chat.schemas import QAGenerateOut, TutorCitation

    m = QAGenerateOut()
    assert m.text == ""
    assert m.citations == []
    assert m.math_blocks == []
    c = TutorCitation(index=1, chunkId="x", authors_short="A", year=None,
                      book_name="B", chapter="ch01", section="1.1", quote="q")
    m2 = QAGenerateOut(text="t", citations=[c], math_blocks=["E=mc^2"])
    assert m2.citations[0].index == 1
    assert "properties" in QAGenerateOut.model_json_schema()


def test_qa_verify_out_shape():
    from src.services.chat.schemas import QAVerifyOut

    m = QAVerifyOut()
    assert m.ok is False
    assert m.unsupported == []
    assert m.confidence == 0.5
    assert m.text == ""
    assert "properties" in QAVerifyOut.model_json_schema()
