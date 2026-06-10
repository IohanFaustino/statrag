import pytest
from types import SimpleNamespace
import src.services.chat.agents.extension_agents.runner as R
from src.services.chat.schemas import ChatRequest


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
    evs = _events(ChatRequest(message="extend something vague", mode="extension"))
    assert any(e.get("type") == "clarify" for e in evs)
    assert evs[-1]["type"] == "done"


def test_normalize_math_parens_to_dollar():
    assert R._normalize_math_delimiters(r"\(E[X]\)") == "$E[X]$"


def test_normalize_math_brackets_to_display():
    result = R._normalize_math_delimiters(r"\[E[X] = \mu\]")
    assert "$$" in result
    assert r"\[" not in result


def test_normalize_math_no_change_for_clean_text():
    assert R._normalize_math_delimiters("plain text $x$ here") == "plain text $x$ here"



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


# ---------------------------------------------------------------------------
# Task 8: new v2 run_extension test — pipeline bridge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_extension_emits_meta_first_then_story_digest(monkeypatch):
    import src.services.chat.agents.extension_agents.runner as R
    from src.services.chat.schemas.output import StoryDigest, Take

    monkeypatch.setattr(R, "parse_catalog", lambda: [SimpleNamespace(slug="hansen-probability"),
                                                     SimpleNamespace(slug="moss")])
    async def fake_resolve(msg, *, catalog, selected_slugs):
        return None, SimpleNamespace(book_slug="hansen-probability", chapter_id="ch07",
                                     requested_subtopics=[])
    monkeypatch.setattr(R, "aresolve_scope_or_clarify", fake_resolve)
    monkeypatch.setattr(R, "fetch_chapter_sections",
                        lambda **k: [{"section_id": "7.4", "h2_path": "7.4 C", "text": "A"}])
    monkeypatch.setattr(R, "_warm_retrieval", lambda slugs: None)

    digest = StoryDigest(book="hansen-probability", chapter="ch07",
                         takes=[Take(heading="h", story="s")])
    async def fake_pipeline(**kwargs):
        kwargs["on_stage"]("story", "Take 1/1 — h")
        return digest, []
    monkeypatch.setattr(R, "run_pipeline", fake_pipeline)

    events = [e async for e in R.run_extension(SimpleNamespace(
        message="Extend 7.4", bookFilter="ALL", model="m", extensionModels=None))]
    assert events[0]["type"] == "meta" and events[0]["mode"] == "extension"
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "StoryDigest" and so["data"]["takes"][0]["heading"] == "h"
    assert any(e["type"] == "stage" and e["stage"] == "story" for e in events)
    assert any(e["type"] == "sources_full" for e in events)
    assert events[-1]["type"] == "done"
