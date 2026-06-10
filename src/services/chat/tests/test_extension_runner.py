import json
import os
import pytest
from types import SimpleNamespace
from src.services.chat.schemas import ChatRequest, ExtensionDigest, ExtensionPoint, ExtensionFootnote
import src.services.chat.agents.extension_agents.runner as R


def _events(req):
    import asyncio
    async def _collect():
        return [e async for e in R.run_extension(req)]
    return asyncio.run(_collect())


def test_clarify_gate_stops_before_agent(monkeypatch):
    monkeypatch.setattr(R, "parse_catalog", lambda: [])
    async def _ascope(*a, **k):
        return {"type": "clarify", "options": ["a", "b"]}, None
    monkeypatch.setattr(R, "aresolve_scope_or_clarify", _ascope)
    monkeypatch.setattr(R, "build_extension_agent",
                        lambda **k: pytest.fail("agent built despite clarify"))
    evs = _events(ChatRequest(message="extend something vague", mode="extension"))
    assert any(e.get("type") == "clarify" for e in evs)
    assert evs[-1]["type"] == "done"


def test_happy_path_streams_points(monkeypatch):
    digest = ExtensionDigest(
        book="hansen-probability", chapter="ch07",
        points=[ExtensionPoint(title="LLN", curated_text="sample mean converges",
                               footnotes=[ExtensionFootnote(marker="1", body="$\\bar X\\to\\mu$",
                                                            source="ross §5.1", kind="corpus")])],
        unfilled_gaps=[])
    monkeypatch.setattr(R, "parse_catalog", lambda: [])
    async def _ascope(*a, **k):
        from src.services.chat.schemas import BookResolution
        return None, BookResolution(book_slug="hansen-probability", book_confidence=0.9,
                                    book_candidates=["hansen-probability"], chapter_id="ch07",
                                    requested_subtopics=[])
    monkeypatch.setattr(R, "aresolve_scope_or_clarify", _ascope)
    monkeypatch.setattr(R, "fetch_chapter_sections",
                        lambda **k: [{"section_id": "7.1", "h2_path": "Intro", "text": "t"}])
    monkeypatch.setattr(R, "_all_slugs", lambda catalog: ["hansen-probability", "ross-probability"])
    async def _run_round(agent, instruction, thread_id):
        return None, json.dumps(digest.model_dump()), [], 10, 20
    monkeypatch.setattr(R, "build_extension_agent", lambda **k: object())
    monkeypatch.setattr(R, "_warm_retrieval", lambda *a, **k: None)
    monkeypatch.setattr(R, "_run_round", _run_round)

    evs = _events(ChatRequest(message="extend hansen ch7", mode="extension"))
    types = [e["type"] for e in evs]
    assert "structured_output" in types
    so = next(e for e in evs if e["type"] == "structured_output")
    assert so["schema"] == "ExtensionDigest"
    assert so["data"]["points"][0]["title"] == "LLN"
    assert evs[-1]["type"] == "done"


def test_round_loop_caps(monkeypatch):
    monkeypatch.setattr(R, "parse_catalog", lambda: [])
    async def _ascope(*a, **k):
        from src.services.chat.schemas import BookResolution
        return None, BookResolution(book_slug="b", book_confidence=0.9, book_candidates=["b"],
                                    chapter_id="ch01", requested_subtopics=[])
    monkeypatch.setattr(R, "aresolve_scope_or_clarify", _ascope)
    monkeypatch.setattr(R, "fetch_chapter_sections", lambda **k: [{"section_id": "1", "h2_path": "i", "text": "t"}])
    monkeypatch.setattr(R, "_all_slugs", lambda catalog: ["b"])
    monkeypatch.setattr(R, "build_extension_agent", lambda **k: object())
    monkeypatch.setattr(R, "_warm_retrieval", lambda *a, **k: None)
    calls = {"n": 0}
    empty = json.dumps(ExtensionDigest(book="b", chapter="ch01", points=[], unfilled_gaps=["q"]).model_dump())
    async def _run_round(agent, instruction, thread_id):
        calls["n"] += 1
        return None, empty, ["q"], 1, 1
    monkeypatch.setattr(R, "_run_round", _run_round)

    evs = _events(ChatRequest(message="extend b ch1", mode="extension", extensionMaxRounds=2))
    assert calls["n"] == 2
    so = next(e for e in evs if e["type"] == "structured_output")
    assert so["data"]["unfilled_gaps"] == ["q"]


def test_normalize_math_parens_to_dollar():
    assert R._normalize_math_delimiters(r"\(E[X]\)") == "$E[X]$"


def test_normalize_math_brackets_to_display():
    result = R._normalize_math_delimiters(r"\[E[X] = \mu\]")
    assert "$$" in result
    assert r"\[" not in result


def test_normalize_math_no_change_for_clean_text():
    assert R._normalize_math_delimiters("plain text $x$ here") == "plain text $x$ here"


def test_strip_md_footnote_markers():
    assert R._strip_md_footnote_markers("text[^1] and [^abc]more") == "text and more"


def test_strip_md_footnote_markers_no_change_clean():
    assert R._strip_md_footnote_markers("no markers here") == "no markers here"


def test_section_chars_default_is_2500():
    assert int(os.environ.get("EXTENSION_SECTION_CHARS", "2500")) == 2500


def test_filter_subtopics_exact_match():
    secs = [
        {"section_id": "7.1", "h2_path": "7.1 Introduction", "text": ""},
        {"section_id": "7.4", "h2_path": "7.4 Chebyshev Inequality", "text": ""},
    ]
    result = R._filter_subtopics(secs, ["chebyshev"], book_slug="hansen")
    assert len(result) == 1
    assert result[0]["section_id"] == "7.4"


def test_filter_subtopics_empty_returns_all():
    secs = [{"section_id": "1", "h2_path": "Intro", "text": ""}]
    assert R._filter_subtopics(secs, [], book_slug="b") == secs


def test_filter_subtopics_no_match_fallback_all(monkeypatch):
    monkeypatch.setattr(R, "hybrid_search", lambda *a, **k: ([], None))
    secs = [{"section_id": "1", "h2_path": "Intro", "text": ""}]
    result = R._filter_subtopics(secs, ["zz_impossible"], book_slug="b")
    assert result == secs


def test_filter_subtopics_fuzzy_match_success(monkeypatch):
    secs = [{"section_id": "7.3", "h2_path": "7.3 Convergence", "text": ""}]
    monkeypatch.setattr(
        R, "hybrid_search",
        lambda *a, **k: ([SimpleNamespace(section="7.3", section_id="")], None)
    )
    result = R._filter_subtopics(secs, ["convergence_typo"], book_slug="b")
    assert result == secs  # fuzzy match found section 7.3


def test_meta_event_emitted_first_with_extension_mode(monkeypatch):
    monkeypatch.setattr(R, "parse_catalog", lambda: [])
    async def _ascope(*a, **k):
        return {"type": "clarify", "options": ["a", "b"]}, None
    monkeypatch.setattr(R, "aresolve_scope_or_clarify", _ascope)
    evs = _events(ChatRequest(message="extend something", mode="extension"))
    assert evs[0]["type"] == "meta"
    assert evs[0]["mode"] == "extension"


def test_run_round_passes_recursion_limit(monkeypatch):
    captured = {}

    class FakeAgent:
        def invoke(self, payload, config):
            captured.update(config)
            return {"messages": [], "files": {}}

    monkeypatch.setenv("EXTENSION_RECURSION_LIMIT", "77")
    import asyncio
    asyncio.run(R._run_round(FakeAgent(), "instr", "tid"))
    assert captured["recursion_limit"] == 77


def test_run_round_recursion_limit_default_100(monkeypatch):
    captured = {}

    class FakeAgent:
        def invoke(self, payload, config):
            captured.update(config)
            return {"messages": [], "files": {}}

    monkeypatch.delenv("EXTENSION_RECURSION_LIMIT", raising=False)
    import asyncio
    asyncio.run(R._run_round(FakeAgent(), "instr", "tid"))
    assert captured["recursion_limit"] == 100


# ---------------------------------------------------------------------------
# T3: authoritative scope stamping in _coerce_digest / _parse_digest
# ---------------------------------------------------------------------------

def test_coerce_digest_overrides_nonempty_model_book_chapter():
    """Model returned non-empty junk; runner must stamp authoritative values."""
    digest_in = ExtensionDigest(
        book="Unknown",
        chapter="7.4–7.8",
        points=[],
        unfilled_gaps=[],
    )
    result = R._coerce_digest(digest_in, book="hansen", chapter="ch07 · 7.4–7.5")
    assert result is not None
    assert result.book == "hansen"
    assert result.chapter == "ch07 · 7.4–7.5"


def test_coerce_digest_overrides_empty_model_book_chapter():
    """Model returned empty strings; runner must still stamp authoritative values."""
    digest_in = ExtensionDigest(book="", chapter="", points=[], unfilled_gaps=[])
    result = R._coerce_digest(digest_in, book="ross", chapter="ch03")
    assert result is not None
    assert result.book == "ross"
    assert result.chapter == "ch03"


def test_coerce_digest_returns_none_for_none_structured():
    assert R._coerce_digest(None, book="b", chapter="c") is None


def test_coerce_digest_returns_none_on_invalid_structured():
    assert R._coerce_digest(object(), book="b", chapter="c") is None


def test_parse_digest_overrides_nonempty_model_book_chapter():
    """JSON parse path must also stamp authoritative values over model output."""
    data = ExtensionDigest(
        book="Unknown", chapter="7.4–7.8", points=[], unfilled_gaps=[]
    ).model_dump()
    text = json.dumps(data)
    result = R._parse_digest(text, book="hansen", chapter="ch07 · 7.4–7.5")
    assert result.book == "hansen"
    assert result.chapter == "ch07 · 7.4–7.5"


def test_parse_digest_stamps_on_parse_failure():
    """Garbage JSON must still produce a digest with authoritative scope."""
    result = R._parse_digest("not json at all }", book="hansen", chapter="ch07")
    assert result.book == "hansen"
    assert result.chapter == "ch07"
    assert "could not parse" in result.unfilled_gaps[0]


# ---------------------------------------------------------------------------
# T3: _scope_label helper
# ---------------------------------------------------------------------------

def test_scope_label_not_narrowed_returns_chapter_id():
    secs = [
        {"section_id": "7.4 Chebyshev Inequality", "h2_path": "...", "text": ""},
        {"section_id": "7.5 WLLN", "h2_path": "...", "text": ""},
    ]
    assert R._scope_label("ch07", secs, narrowed=False) == "ch07"


def test_scope_label_narrowed_single_section():
    secs = [{"section_id": "7.4 Chebyshev Inequality", "h2_path": "...", "text": ""}]
    assert R._scope_label("ch07", secs, narrowed=True) == "ch07 · 7.4"


def test_scope_label_narrowed_multi_section():
    secs = [
        {"section_id": "7.4 Chebyshev Inequality", "h2_path": "...", "text": ""},
        {"section_id": "7.5 WLLN", "h2_path": "...", "text": ""},
    ]
    assert R._scope_label("ch07", secs, narrowed=True) == "ch07 · 7.4–7.5"


def test_scope_label_no_numeric_prefix_falls_back_to_chapter_id():
    secs = [{"section_id": "Introduction", "h2_path": "...", "text": ""}]
    assert R._scope_label("ch07", secs, narrowed=True) == "ch07"


def test_scope_label_empty_sections_returns_chapter_id():
    assert R._scope_label("ch07", [], narrowed=True) == "ch07"


# ---------------------------------------------------------------------------
# T3: _filter_subtopics regression — realistic Hansen ch07 fixture
# ---------------------------------------------------------------------------

def _hansen_ch07_sections():
    """Realistic section fixture for Hansen ch07 (7.1–7.8)."""
    return [
        {"section_id": f"7.{i} {label}", "h2_path": f"Hansen | ch07 | 7.{i} {label}", "text": ""}
        for i, label in [
            (1, "Introduction"),
            (2, "Modes of Convergence"),
            (3, "Convergence in Mean Square"),
            (4, "Chebyshev Inequality"),
            (5, "Weak Law of Large Numbers"),
            (6, "Strong Law of Large Numbers"),
            (7, "Uniform Law of Large Numbers"),
            (8, "Exercises"),
        ]
    ]


def test_filter_subtopics_regression_chebyshev_wlln():
    """Needle ['7.4 Chebyshev', '7.5 WLLN'] must keep EXACTLY sections 7.4 + 7.5."""
    secs = _hansen_ch07_sections()
    result = R._filter_subtopics(secs, ["7.4 Chebyshev", "7.5 WLLN"], book_slug="hansen")
    ids = [s["section_id"].split()[0] for s in result]
    assert ids == ["7.4", "7.5"], f"Expected ['7.4', '7.5'], got {ids}"


def test_filter_subtopics_numeric_needle_no_false_positive():
    """Needle '7.4' must not match a hypothetical section '17.4'."""
    secs = [
        {"section_id": "7.4 Chebyshev Inequality", "h2_path": "7.4 Chebyshev", "text": ""},
        {"section_id": "17.4 Something Else", "h2_path": "17.4 Something Else", "text": ""},
    ]
    result = R._filter_subtopics(secs, ["7.4"], book_slug="b")
    assert len(result) == 1
    assert result[0]["section_id"].startswith("7.4")


def test_needle_matches_no_trailing_digit_false_positive():
    """Needle '7.4' must NOT match section label '7.40 Something'."""
    # "7.40" has a trailing digit after "7.4" — the word-boundary regex
    # (?![.\d]) must reject it.
    assert not R._needle_matches("7.4", "7.40 something")


# ---------------------------------------------------------------------------
# T3: _scope_label non-contiguous range approximation
# ---------------------------------------------------------------------------

def test_scope_label_non_contiguous_range_is_first_to_last():
    """Non-contiguous sections (7.2 + 7.5, skipping 7.3/7.4) produce first–last
    range label.  This is a known approximation: _scope_label uses nums[0]–nums[-1]
    and does NOT attempt to express gaps (e.g. "7.2 + 7.5")."""
    secs = [
        {"section_id": "7.2 Modes of Convergence", "h2_path": "...", "text": ""},
        {"section_id": "7.5 Weak Law of Large Numbers", "h2_path": "...", "text": ""},
    ]
    label = R._scope_label("ch07", secs, narrowed=True)
    assert label == "ch07 · 7.2–7.5"
