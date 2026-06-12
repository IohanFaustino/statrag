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


# ---------------------------------------------------------------------------
# UUID section_id headings — the live-found bug
# ---------------------------------------------------------------------------

HEADINGS_UUID = [
    {"section_id": "uuid-73", "h2_path": "7.3 CONVERGENCE IN PROBABILITY"},
    {"section_id": "uuid-74", "h2_path": "7.4 CHEBYSHEV'S INEQUALITY"},
    {"section_id": "uuid-75", "h2_path": "7.5 WEAK LAW OF LARGE NUMBERS"},
]


def test_explicit_number_matches_leading_h2_number_not_uuid():
    sid, score = resolve_section("teach me section 7.4", subtopics=["7.4"], headings=HEADINGS_UUID)
    assert sid == "uuid-74" and score == 1.0


def test_explicit_number_beats_conflicting_words():
    # "7.4" explicit must win even though the words say "law of large numbers" (which is 7.5)
    sid, score = resolve_section(
        "section 7.4, the Law of Large Numbers",
        subtopics=["7.4", "the Law of Large Numbers"],
        headings=HEADINGS_UUID,
    )
    assert sid == "uuid-74" and score == 1.0
