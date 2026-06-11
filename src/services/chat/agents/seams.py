"""Pure-code narrative-seam validator for the tutor mode.

Zero LLM. Verifies that the body beats (intro excluded) form one woven
narrative: each present beat's opening sentence connects to the previous
present beat's closing sentence OR to the plan thesis; openers are not
boilerplate; and the prose stays in English (guards the known long-run
language-drift bug). Returns scores that ride the existing
``TutorAnswer.quality`` dict.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Intro (``tldr``) is deliberately absent — the thread is defined over body beats.
BEAT_ORDER = [
    "definition",
    "formal_statement",
    "example_intuition",
    "applications",
    "further_reading",
]

# Small English function-word set: presence ratio discriminates English prose
# from drift (e.g. Polish) without an LLM.
_EN_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "is", "are", "in", "on", "that",
    "this", "with", "as", "for", "we", "it", "by", "from", "be", "which", "when",
}
_LANG_FLOOR = 0.06  # >=6% of tokens must be English function words

_WORD_RE = re.compile(r"[A-Za-zÀ-ſ]+")
# Matches display ($$…$$) and inline ($…$) LaTeX regions.  Must be applied
# before any prose-level analysis so math tokens never pollute sentence
# splitting, lemma overlap, or language-ratio calculation.
_MATH_RE = re.compile(
    r"\$\$.+?\$\$"                              # display: $$…$$
    r"|\$(?=[^$]*[\\^_{}\[\]])(?:[^$])+?\$",   # inline: must contain a LaTeX indicator
    re.DOTALL,
)
# Split only at a boundary followed by whitespace + an uppercase letter so that
# abbreviations like "Fig. 7." or "e.g. linear" stay as single units.
# NOTE: _lang_ratio / the _LANG_FLOOR is calibrated for paragraph-length beats,
# not single terse sentences — short beats may produce unreliable language scores.
_SENT_SPLIT = re.compile(r"(?<=[.!?])(?=\s+[A-Z])")
# Topical-null words excluded from seam lemma-overlap: function words,
# prepositions, conjunctions, auxiliaries, generic connectives and pronouns.
# These carry no topical signal, so two unrelated sentences must NOT count as
# connected merely because they share one of them (e.g. "into").
_GENERIC = _EN_STOP | {
    # generic discourse connectives
    "now", "then", "next", "here", "there", "these", "those", "same", "also",
    "thus", "hence", "therefore", "however", "moreover", "first", "second",
    "third", "above", "below", "follows", "consider", "see", "while", "where",
    "what", "how", "why", "but", "so", "yet", "because", "since", "although",
    # prepositions
    "into", "onto", "over", "under", "between", "through", "across", "within",
    "without", "about", "against", "toward", "towards", "upon", "per", "via",
    "than", "out", "off", "up", "down", "at", "not", "no", "nor", "if", "else",
    # auxiliaries / modals / common verbs with no topical signal
    "can", "will", "would", "could", "should", "may", "might", "must", "has",
    "have", "had", "was", "were", "been", "being", "do", "does", "did", "get",
    "gets", "make", "makes", "let", "lets",
    # pronouns / determiners / quantifiers
    "its", "their", "them", "they", "our", "your", "his", "her", "you", "he",
    "she", "more", "most", "some", "any", "each", "both", "all", "one", "two",
    "three", "such", "very", "only", "just", "many", "much", "few", "every",
}


@dataclass
class SeamResult:
    passed: bool
    failing_seams: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)


def _strip_math(text: str) -> str:
    """Remove display ($$…$$) and inline ($…$) LaTeX so math tokens never
    pollute seam prose (sentence splitting, lemma overlap, language ratio)."""
    return _MATH_RE.sub(" ", text)


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _content_lemmas(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _GENERIC and len(t) > 2}


def _sentences(text: str) -> list[str]:
    text = _strip_math(text)
    parts = [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]
    return parts


def _first_sentence(text: str) -> str:
    s = _sentences(text)
    return s[0] if s else ""


def _last_sentence(text: str) -> str:
    """Return the last topically-rich sentence for seam anchoring.

    Falls back through prior sentences so that a trailing transitional clause
    (e.g. "See Fig. 7." with only a single short lemma) does not become the
    sole seam anchor and produce a false seam failure.
    """
    sents = _sentences(text)
    for sent in reversed(sents):
        if len(_content_lemmas(sent)) >= 2:
            return sent
    return sents[-1] if sents else ""


def _leading_trigram(text: str) -> str:
    toks = _tokens(_first_sentence(text))
    return " ".join(toks[:3])


def _lang_ratio(text: str) -> float:
    toks = _tokens(_strip_math(text))
    if not toks:
        return 1.0
    return sum(1 for t in toks if t in _EN_STOP) / len(toks)


def check_seams(beats: dict[str, str], thesis: str = "") -> SeamResult:
    """Validate the narrative seams over the *present* body beats.

    ``beats`` maps aspect key -> markdown string. ``thesis`` is the synthesis
    plan throughline (may be empty -> seam-only validation)."""
    present = [(k, beats.get(k, "") or "") for k in BEAT_ORDER]
    present = [(k, v) for k, v in present if v.strip()]

    thesis_lemmas = _content_lemmas(thesis)
    failing: list[str] = []

    # 1. Seam continuity (adjacent present beats; first beat has no inbound seam).
    seam_total = max(len(present) - 1, 0)
    seam_pass = 0
    for (pk, pv), (ck, cv) in zip(present, present[1:]):
        prev_lemmas = _content_lemmas(_last_sentence(pv))
        cur_lemmas = _content_lemmas(_first_sentence(cv))
        connected = bool(cur_lemmas & prev_lemmas) or bool(cur_lemmas & thesis_lemmas)
        if connected:
            seam_pass += 1
        else:
            failing.append(
                f"seam {pk}->{ck}: opener has no lemma overlap with prior close "
                f"or thesis"
            )
    seam_continuity = (seam_pass / seam_total) if seam_total else 1.0

    # 2. Boilerplate: >=2 present beats opening with the same leading 3-gram.
    trigrams: dict[str, list[str]] = {}
    for k, v in present:
        tg = _leading_trigram(v)
        if tg:
            trigrams.setdefault(tg, []).append(k)
    for tg, keys in trigrams.items():
        if len(keys) >= 2:
            failing.append(f"boilerplate openers ({tg!r}) in beats: {', '.join(keys)}")

    # 3. Language drift.
    lang_ok = 1.0
    for k, v in present:
        if _lang_ratio(v) < _LANG_FLOOR:
            lang_ok = 0.0
            failing.append(f"beat {k}: language-drift (English function-word ratio below floor)")

    passed = (seam_continuity >= 1.0) and lang_ok >= 1.0 and not any(
        f.startswith("boilerplate") for f in failing
    )
    return SeamResult(
        passed=passed,
        failing_seams=failing,
        scores={
            "seam_continuity": round(seam_continuity, 3),
            "lang_ok": lang_ok,
            "thesis_adherence": round(
                _thesis_adherence(beats, thesis_lemmas), 3
            ),
        },
    )


def _thesis_adherence(beats: dict[str, str], thesis_lemmas: set[str]) -> float:
    """Fraction of beats (incl. tldr) sharing >=1 lemma with the thesis.
    Reported only — never gates (overlap is too noisy to fail on)."""
    if not thesis_lemmas:
        return 0.0
    keys = ["tldr"] + BEAT_ORDER
    vals = [(beats.get(k, "") or "") for k in keys]
    present = [v for v in vals if v.strip()]
    if not present:
        return 0.0
    hits = sum(1 for v in present if _content_lemmas(v) & thesis_lemmas)
    return hits / len(present)
