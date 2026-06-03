# src/services/chat/tests/test_ts_components_compare.py
"""Unit tests for the time-series-components comparison eval (pure helpers only)."""
from src.services.chat.eval import ts_components_compare as tc


def test_constants_present():
    assert "components of a time series" in tc.QUESTION.lower()
    assert tc.BOOKS == ["cerqueira", "spark_ts", "pesaran"]
    assert tc.JUDGE_MODEL == "gpt-5.4-nano-2026-03-17"
    assert tc.API_MODELS == [
        "gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "qwen-plus",
    ]
    for c in ("trend", "seasonal", "cyclical", "irregular"):
        assert any(c in g.lower() for g in tc.GOLD_COMPONENTS)
    assert tc.MAX_TOK == 700
    assert tc.TIMEOUT_S == 60


def test_prompt_mentions_question_and_json():
    assert "components of a time series" in tc.ANSWER_PROMPT.lower()
    assert '"reasoning"' in tc.ANSWER_PROMPT
    assert '"answer"' in tc.ANSWER_PROMPT


def test_contestant_filename_map():
    assert tc.CONTESTANT_FILE["gpt-5.4-nano-2026-03-17"] == "nano.json"
    assert tc.CONTESTANT_FILE["sonnet"] == "sonnet.json"
    assert tc.CONTESTANT_FILE["opus"] == "opus.json"


def test_format_context_renders_sources():
    from src.services.chat.schemas import Source
    s = Source(
        rank=1, book="cerqueira", chapter="ch03", section="3.1",
        title="Time Series Decomposition", excerpt="", score=0.9,
        chunkId="x1", chunk="A time series has trend and seasonality.",
        book_name="DL for Time Series", authors_short="Cerqueira",
        page_from=40, page_to=42,
    )
    out = tc._format_context([s])
    assert "[1]" in out
    assert "Time Series Decomposition" in out
    assert "trend and seasonality" in out
    assert "Cerqueira" in out


def test_parse_answer_strips_fences_and_extracts():
    raw = '```json\n{"reasoning":"r","answer":"Trend and seasonality."}\n```'
    assert tc._parse_answer(raw) == "Trend and seasonality."


def test_parse_answer_bad_json_returns_raw_stripped():
    assert tc._parse_answer("not json at all") == "not json at all"


def test_write_answer_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(tc, "_ANSWERS", tmp_path)
    tc._write_answer("qwen-plus", model="qwen-plus", answer="A.", in_tok=10,
                     out_tok=5, ms=123, ok=True, err="")
    data = tc._load_answers()
    assert data["qwen-plus"]["answer"] == "A."
    assert data["qwen-plus"]["ok"] is True
    assert data["qwen-plus"]["out_tok"] == 5


def test_parse_judge_ok_and_fallback():
    good = '{"clarity":5,"faithfulness":4,"coverage":3,"conciseness":4}'
    d = tc._parse_judge(good)
    assert d == {"clarity": 5.0, "faithfulness": 4.0, "coverage": 3.0,
                 "conciseness": 4.0, "overall": 4.0}
    bad = tc._parse_judge("garbage")
    assert bad["overall"] == 0.0
    assert bad["clarity"] == 0.0


def test_render_artifact_has_table_and_answers():
    answers = {
        "gpt-5.4-nano-2026-03-17": {
            "contestant": "gpt-5.4-nano-2026-03-17", "model": "gpt-5.4-nano-2026-03-17",
            "answer": "Trend, seasonal, cyclical, irregular.", "in_tok": 500,
            "out_tok": 200, "ms": 1200, "ok": True, "err": "",
        },
        "sonnet": {
            "contestant": "sonnet", "model": "claude-sonnet", "answer": "Four parts.",
            "in_tok": 0, "out_tok": 0, "ms": 0, "ok": True, "err": "",
        },
    }
    scores = {
        "gpt-5.4-nano-2026-03-17": {"clarity": 5.0, "faithfulness": 5.0,
                                    "coverage": 5.0, "conciseness": 4.0, "overall": 4.75},
        "sonnet": {"clarity": 4.0, "faithfulness": 4.0, "coverage": 3.0,
                   "conciseness": 5.0, "overall": 4.0},
    }
    md = tc._render_artifact(answers, scores)
    assert "| contestant |" in md
    assert "gpt-5.4-nano-2026-03-17" in md
    assert "4.75" in md
    assert "$" in md
    assert "## Full answers" in md
    assert "Trend, seasonal, cyclical, irregular." in md
    assert "_(agent — no API cost)_" in md or "n/a" in md
