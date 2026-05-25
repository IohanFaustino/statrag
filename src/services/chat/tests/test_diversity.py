"""Unit tests for the author-diversity retrieval step.

Coverage:
  - ``author_key`` normalisation
  - ``diversify_section_keys`` round-robin + year-spread tiebreak
  - target_authors < 2 → plain slice (unchanged order)
  - fewer authors than target → graceful saturation
  - ``build_author_filter_from_candidates`` exclusion logic
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Path setup so the module is importable without a full project install.
# ---------------------------------------------------------------------------
_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")
os.environ.setdefault("TUTOR_DEEP_WARM", "0")

import pytest

from src.services.chat.retrievers.diversity import (
    AuthorMeta,
    author_key,
    build_author_filter_from_candidates,
    diversify_section_keys,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _meta(
    authors_short: str = "",
    authors: str = "",
    book: str = "",
    year: int | None = None,
    score: float = 1.0,
) -> AuthorMeta:
    return AuthorMeta(
        authors_short=authors_short,
        authors=authors,
        book=book,
        year=year,
        score=score,
    )


def _key(book: str, section: str) -> tuple[str, str]:
    return (book, section)


# ---------------------------------------------------------------------------
# author_key
# ---------------------------------------------------------------------------


class TestAuthorKey:
    def test_prefers_authors_short(self):
        m = _meta(authors_short="Smith et al.", authors="Smith, Doe", book="islp")
        assert author_key(m) == "smith et al."

    def test_falls_back_to_authors_when_no_short(self):
        m = _meta(authors_short="", authors="Smith, Doe", book="islp")
        assert author_key(m) == "smith, doe"

    def test_falls_back_to_book_when_no_authors(self):
        m = _meta(authors_short="", authors="", book="islp")
        assert author_key(m) == "islp"

    def test_strips_and_lowercases(self):
        m = _meta(authors_short="  HASTIE et al.  ")
        assert author_key(m) == "hastie et al."

    def test_empty_returns_empty(self):
        m = _meta()
        assert author_key(m) == ""


# ---------------------------------------------------------------------------
# diversify_section_keys — target < 2 preserves plain slice
# ---------------------------------------------------------------------------


class TestDiversifyTarget0or1:
    """With target_authors < 2 the function must return the plain top-N slice."""

    def _build_scenario(self):
        """6 sections from 2 authors, descending score."""
        keys = [
            _key("islp", "2.1"),  # score 1.0, Smith
            _key("islp", "2.2"),  # score 0.9, Smith
            _key("esl",  "3.1"),  # score 0.8, Hastie
            _key("islp", "2.3"),  # score 0.7, Smith
            _key("esl",  "3.2"),  # score 0.6, Hastie
            _key("esl",  "3.3"),  # score 0.5, Hastie
        ]
        meta = {
            _key("islp", "2.1"): _meta("Smith", "Smith, James", "islp", 2021, 1.0),
            _key("islp", "2.2"): _meta("Smith", "Smith, James", "islp", 2021, 0.9),
            _key("esl",  "3.1"): _meta("Hastie", "Hastie, Tibshirani", "esl", 2009, 0.8),
            _key("islp", "2.3"): _meta("Smith", "Smith, James", "islp", 2021, 0.7),
            _key("esl",  "3.2"): _meta("Hastie", "Hastie, Tibshirani", "esl", 2009, 0.6),
            _key("esl",  "3.3"): _meta("Hastie", "Hastie, Tibshirani", "esl", 2009, 0.5),
        }
        return keys, meta

    def test_target_0_returns_top_n_slice(self):
        keys, meta = self._build_scenario()
        result = diversify_section_keys(keys, meta, target_authors=0, top_sections=4)
        assert result == keys[:4]

    def test_target_1_returns_top_n_slice(self):
        keys, meta = self._build_scenario()
        result = diversify_section_keys(keys, meta, target_authors=1, top_sections=3)
        assert result == keys[:3]


# ---------------------------------------------------------------------------
# diversify_section_keys — round-robin interleaving
# ---------------------------------------------------------------------------


class TestDiversifyRoundRobin:
    """6 sections from 2 authors, target 3 → result interleaves."""

    def _scenario_two_authors(self):
        # 3 Smith (scores 1.0, 0.8, 0.6) and 3 Hastie (scores 0.9, 0.7, 0.5)
        keys = [
            _key("islp", "s1"),  # Smith  1.0
            _key("esl",  "h1"),  # Hastie 0.9
            _key("islp", "s2"),  # Smith  0.8
            _key("esl",  "h2"),  # Hastie 0.7
            _key("islp", "s3"),  # Smith  0.6
            _key("esl",  "h3"),  # Hastie 0.5
        ]
        meta = {
            _key("islp", "s1"): _meta("Smith", score=1.0, year=2021),
            _key("esl",  "h1"): _meta("Hastie", score=0.9, year=2009),
            _key("islp", "s2"): _meta("Smith", score=0.8, year=2021),
            _key("esl",  "h2"): _meta("Hastie", score=0.7, year=2009),
            _key("islp", "s3"): _meta("Smith", score=0.6, year=2021),
            _key("esl",  "h3"): _meta("Hastie", score=0.5, year=2009),
        }
        return keys, meta

    def test_first_two_slots_are_different_authors(self):
        keys, meta = self._scenario_two_authors()
        result = diversify_section_keys(keys, meta, target_authors=3, top_sections=4)
        assert len(result) == 4
        a0 = author_key(meta[result[0]])
        a1 = author_key(meta[result[1]])
        assert a0 != a1, "First two picks should be from different authors"

    def test_result_contains_both_authors(self):
        keys, meta = self._scenario_two_authors()
        result = diversify_section_keys(keys, meta, target_authors=3, top_sections=4)
        authors_in_result = {author_key(meta[k]) for k in result}
        assert "smith" in authors_in_result
        assert "hastie" in authors_in_result

    def test_total_count_correct(self):
        keys, meta = self._scenario_two_authors()
        result = diversify_section_keys(keys, meta, target_authors=3, top_sections=4)
        assert len(result) == 4

    def test_no_duplicates(self):
        keys, meta = self._scenario_two_authors()
        result = diversify_section_keys(keys, meta, target_authors=3, top_sections=6)
        assert len(result) == len(set(result))

    def test_target_1_unchanged_order(self):
        keys, meta = self._scenario_two_authors()
        result = diversify_section_keys(keys, meta, target_authors=1, top_sections=4)
        assert result == keys[:4], "target=1 must preserve original order"

    def test_more_authors_than_target_saturates_gracefully(self):
        """Only 2 distinct authors available but target is 3 — should still fill 4 slots."""
        keys, meta = self._scenario_two_authors()
        result = diversify_section_keys(keys, meta, target_authors=3, top_sections=4)
        assert len(result) == 4


# ---------------------------------------------------------------------------
# diversify_section_keys — three distinct authors
# ---------------------------------------------------------------------------


class TestDiversifyThreeAuthors:
    def _scenario(self):
        keys = [
            _key("a", "1"),  # Author A  score 1.0
            _key("b", "1"),  # Author B  score 0.9
            _key("c", "1"),  # Author C  score 0.8
            _key("a", "2"),  # Author A  score 0.7
            _key("b", "2"),  # Author B  score 0.6
            _key("c", "2"),  # Author C  score 0.5
        ]
        meta = {
            _key("a", "1"): _meta("AuthorA", score=1.0, year=2020),
            _key("b", "1"): _meta("AuthorB", score=0.9, year=2018),
            _key("c", "1"): _meta("AuthorC", score=0.8, year=2015),
            _key("a", "2"): _meta("AuthorA", score=0.7, year=2020),
            _key("b", "2"): _meta("AuthorB", score=0.6, year=2018),
            _key("c", "2"): _meta("AuthorC", score=0.5, year=2015),
        }
        return keys, meta

    def test_first_three_slots_are_distinct_authors(self):
        keys, meta = self._scenario()
        result = diversify_section_keys(keys, meta, target_authors=3, top_sections=4)
        assert len(result) >= 3
        first_three_authors = [author_key(meta[result[i]]) for i in range(3)]
        assert len(set(first_three_authors)) == 3, (
            f"First 3 slots should be 3 distinct authors, got {first_three_authors}"
        )

    def test_all_three_authors_represented_in_four_slots(self):
        keys, meta = self._scenario()
        result = diversify_section_keys(keys, meta, target_authors=3, top_sections=4)
        assert {author_key(meta[k]) for k in result} == {"authora", "authorb", "authorc"}


# ---------------------------------------------------------------------------
# diversify_section_keys — empty / edge cases
# ---------------------------------------------------------------------------


class TestDiversifyEdgeCases:
    def test_empty_returns_empty(self):
        assert diversify_section_keys([], {}, target_authors=3, top_sections=4) == []

    def test_top_sections_zero(self):
        keys = [_key("a", "1"), _key("b", "1")]
        meta = {
            _key("a", "1"): _meta("A", score=1.0),
            _key("b", "1"): _meta("B", score=0.9),
        }
        result = diversify_section_keys(keys, meta, target_authors=2, top_sections=0)
        assert result == []

    def test_single_key_returns_that_key(self):
        keys = [_key("a", "1")]
        meta = {_key("a", "1"): _meta("A", score=1.0)}
        result = diversify_section_keys(keys, meta, target_authors=3, top_sections=2)
        assert result == [_key("a", "1")]

    def test_missing_meta_key_treated_as_unknown_author(self):
        """Keys without entries in key_meta are grouped under '' author."""
        keys = [_key("x", "1"), _key("y", "1")]
        meta = {_key("x", "1"): _meta("X", score=1.0)}
        # _key("y", "1") has no meta — should not crash
        result = diversify_section_keys(keys, meta, target_authors=2, top_sections=2)
        assert len(result) == 2
        assert set(result) == {_key("x", "1"), _key("y", "1")}


# ---------------------------------------------------------------------------
# build_author_filter_from_candidates
# ---------------------------------------------------------------------------


class _FakeSrc:
    """Minimal Source-like stub."""
    def __init__(self, authors_short: str, authors: str = "", book: str = ""):
        self.authors_short = authors_short
        self.authors = authors
        self.book = book


class TestBuildAuthorFilter:
    def test_excludes_matching_authors(self):
        cands = [
            _FakeSrc("Smith"),
            _FakeSrc("Hastie"),
            _FakeSrc("Bishop"),
        ]
        result = build_author_filter_from_candidates({"smith", "hastie"}, cands)
        assert len(result) == 1
        assert result[0].authors_short == "Bishop"

    def test_empty_exclusion_returns_all(self):
        cands = [_FakeSrc("A"), _FakeSrc("B")]
        assert build_author_filter_from_candidates(set(), cands) == cands

    def test_all_excluded_returns_empty(self):
        cands = [_FakeSrc("A"), _FakeSrc("B")]
        assert build_author_filter_from_candidates({"a", "b"}, cands) == []

    def test_empty_candidates_returns_empty(self):
        assert build_author_filter_from_candidates({"a"}, []) == []


class TestResolveDiversity:
    """deep_tutor._resolve_diversity: request value -> (mode, cap)."""

    def _r(self):
        from src.services.chat.agents.deep_tutor import _resolve_diversity
        return _resolve_diversity

    def test_off_for_0_and_1(self):
        r = self._r()
        assert r(0) == ("off", 0)
        assert r(1) == ("off", 0)

    def test_auto_string(self):
        mode, cap = self._r()("auto")
        assert mode == "auto" and cap >= 2

    def test_none_defaults_to_auto_when_enabled(self):
        mode, _ = self._r()(None)
        assert mode in ("auto", "off")  # off only if TUTOR_DIVERSITY=0 in env

    def test_fixed_caps_to_max(self):
        from src.services.chat.agents.deep_tutor import _DIVERSITY_MAX, _resolve_diversity
        assert _resolve_diversity(3) == ("fixed", min(3, _DIVERSITY_MAX))
        assert _resolve_diversity(99) == ("fixed", _DIVERSITY_MAX)
