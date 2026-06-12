# src/services/chat/tests/test_resolve_section.py
from src.services.chat.agents._scope import resolve_section, section_clarify


HEADINGS = [
    {"section_id": "7.3", "h2_path": "7.3 The Sample Mean"},
    {"section_id": "7.4", "h2_path": "7.4 Law of Large Numbers"},
    {"section_id": "7.5", "h2_path": "7.5 Central Limit Theorem"},
]


def test_explicit_section_number_is_deterministic():
    sid, score = resolve_section("teach me 7.4", subtopics=["7.4"], headings=HEADINGS)
    assert sid == "7.4" and score == 1.0


def test_no_number_matches_heading_by_words():
    sid, score = resolve_section("explain the law of large numbers",
                                 subtopics=["law of large numbers"], headings=HEADINGS)
    assert sid == "7.4" and score >= 0.5


def test_low_match_returns_empty_section():
    sid, score = resolve_section("tell me about quantum entanglement",
                                 subtopics=["quantum entanglement"], headings=HEADINGS)
    assert sid == "" and score < 0.5


def test_section_clarify_when_no_section_resolved():
    ev = section_clarify(headings=HEADINGS, chapter_id="ch07")
    assert ev["type"] == "clarify" and ev["reason"] == "section_ambiguous"
    assert len(ev["candidates"]) == 3
