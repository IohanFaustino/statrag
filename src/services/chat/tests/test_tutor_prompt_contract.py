"""Prompt-contract tests for the deep-tutor system message.

These lock in the *directives* that shape the tutor answer's format so an
accidental edit cannot silently drop them. They do NOT evaluate live LLM
output — semantic quality is checked by running a real tutor query (see
docs/services/chat-features/36-deep-tutor.md). Each test maps to a refine
item from the 2026-05-20 formatting pass.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")
_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.services.chat.prompts.deep_tutor import (  # noqa: E402
    ASPECT_HEADINGS,
    DEEP_TUTOR_INSTRUCTIONS,
    EXTRACT_CONCEPTS_BUDGET_PROMPT,
)

# Normalise whitespace so phrase checks are insensitive to line wrapping.
INSTR = " ".join(DEEP_TUTOR_INSTRUCTIONS.lower().split())
INSTR_PLANNER = " ".join(EXTRACT_CONCEPTS_BUDGET_PROMPT.lower().split())


# --- #2 rename ----------------------------------------------------------
def test_intro_heading_renamed():
    assert ASPECT_HEADINGS["tldr"] == "Introduction"


# --- #3 structure into left-aligned subsections (§12) ------------------
def test_structure_requires_subsection_headers():
    assert "wall of text" in INSTR
    # ### H3 headers remain the backbone of each aspect body
    assert "left-aligned subsection headers" in INSTR
    # C-style: inside each ### subsection, use bold-lead-in bullets, one per claim
    assert "bold lead-in bullets" in INSTR
    assert "one claim per line" in INSTR
    # the old prose mandate is gone — no flat 3-5 sentence paragraph rule,
    # no blanket bullet ban
    assert "3-5 sentences" not in INSTR
    assert "not bullet lists" not in INSTR
    # definition gets a ### per component and a ### for the central quantity
    assert "### bias" in INSTR
    assert "### mse" in INSTR
    # component/decomposition formulas must be CENTERED DISPLAY equations ($$)
    assert "centered display equations" in INSTR
    assert "not inline" in INSTR
    # density: bullets must stay substantive and explain where the concept fits
    assert "depth over brevity" in INSTR
    assert "where it fits" in INSTR
    # draft is invited to be extensive — ranges are minimums, not caps
    assert "be extensive" in INSTR
    assert "minimums, not caps" in INSTR


def test_math_and_figures_placed_in_subsection():
    # display math is placed inside the ### subsection it belongs to,
    # never piled at the end
    assert "inside the" in INSTR and "subsection it belongs to" in INSTR
    # each Example case states its formula and carries its figure marker
    # within that case's subsection
    assert "each example" in INSTR
    assert "in that same subsection" in INSTR or "within that same subsection" in INSTR


# --- #4 intro = summary + roadmap --------------------------------------
def test_intro_has_summary_then_roadmap():
    # tldr block must ask for both the direct answer and a roadmap preview
    assert "roadmap" in INSTR or "road ahead" in INSTR
    assert "previews" in INSTR or "preview the road" in INSTR
    # schema description carries the roadmap contract too
    from src.services.chat.schemas.output import DeepTutorAnswer

    desc = DeepTutorAnswer.model_fields["tldr"].description.lower()
    assert "roadmap" in desc


# --- #5 further reading = research questions ---------------------------
def test_further_reading_asks_research_questions():
    assert "research question" in INSTR
    from src.services.chat.schemas.output import DeepTutorAnswer

    desc = DeepTutorAnswer.model_fields["further_reading"].description.lower()
    assert "research question" in desc


# --- #6 per-source attribution -----------------------------------------
def test_per_claim_attribution_required():
    assert "attribution is per-claim" in INSTR
    assert "do not pool two sources" in INSTR
    # definition field explicitly warns against merging sources
    assert "audit who contributed what" in INSTR


# --- #7 formal statement: conditional verbatim, else empty (Block B) ---
def test_formal_statement_verbatim_contract():
    # verbatim is REQUIRED only when a numbered statement exists in sources
    assert "when such a statement exists" in INSTR
    assert "conforming to" in INSTR
    assert "word for word" in INSTR
    assert "not one comma different" in INSTR
    assert "overrides the ~15-word limit" in INSTR
    # when NO numbered statement exists, the field must be empty (not invented)
    assert "emit an empty string" in INSTR
    assert "numbered formal statement" in INSTR
    assert "never present a paraphrase as if it were a verbatim quote" in INSTR


# --- Block B: definition build-up + applications grouping --------------
def test_definition_framing_and_buildup_contract():
    # definition opens with a framing sentence then ### subsections per component
    assert "open with one framing sentence" in INSTR
    assert "one ``### `` subsection per named component" in INSTR
    assert "graphical hand-off" in INSTR


# --- §11 Block D: formulas have a home + long-context organizer --------
def test_definition_formulas_have_a_home_contract():
    # §11 fix: formulas + central decomposition (MSE) live in definition when
    # formal_statement is empty — must NOT be deferred away.
    assert "formulas have a home here" in INSTR
    assert "do not\n    defer the formulas" in INSTR or "do not defer the formulas" in INSTR


def test_organizer_preamble_contract():
    from src.services.chat.prompts.deep_tutor import ORGANIZER_PREAMBLE

    p = " ".join(ORGANIZER_PREAMBLE.lower().split())
    assert "long-context organizer" in p
    assert "read all of it" in p
    assert "defining formulas" in p
    assert "real, specific application cases" in p


def test_organize_workflow_resolves():
    from types import SimpleNamespace
    from src.services.chat.agents.deep_tutor import _resolve_workflow

    assert _resolve_workflow(SimpleNamespace(tutorWorkflow="organize")) == "organize"
    assert _resolve_workflow(SimpleNamespace(tutorWorkflow="orchestrator")) == "orchestrator"
    assert _resolve_workflow(SimpleNamespace(tutorWorkflow=None)) == "single"
    assert _resolve_workflow(SimpleNamespace(tutorWorkflow="bogus")) == "single"


def test_build_organize_pool_token_budget():
    from src.services.chat.agents.deep_tutor import _build_organize_pool
    from src.services.chat.schemas import Source

    def mk(i: str, n: int) -> Source:
        return Source(rank=1, book="b", chapter="c", section="s", title="t",
                      excerpt="x", score=0.5, chunkId=i, chunk="w " * n)
    # each chunk ~ (2n chars)//4 tokens; budget forces a cut
    cands = [mk(str(i), 400) for i in range(20)]
    ranked = cands[:3]
    pool = _build_organize_pool("q", cands, ranked, max_tokens=600)
    assert 0 < len(pool) < len(cands)            # trimmed by budget
    assert pool[0].chunkId in {"0", "1", "2"}     # density-ranked included first


def test_planner_emits_application_case_facet():
    assert "application-case facet" in INSTR_PLANNER
    assert "application or empirical case" in INSTR_PLANNER


# --- §12 Block F: every inline marker gets a linkable citation ----------
def test_ensure_marker_citations_fills_gaps():
    from src.services.chat.agents.deep_tutor import _ensure_marker_citations
    from src.services.chat.schemas import Source
    from src.services.chat.schemas.output import TutorCitation

    sources = [
        Source(rank=1, book="islp", chapter="ch2", section="2.2", title="t",
               excerpt="bias variance", score=0.9, chunkId="c1", chunk="bias variance"),
        Source(rank=2, book="wool", chapter="ch3", section="3.1", title="t",
               excerpt="omitted var", score=0.8, chunkId="c2", chunk="omitted var"),
    ]
    text = "Bias matters [1]. Variance too [2]. Decomposition [3]."
    enriched = [TutorCitation(index=1, chunkId="c1")]   # model only cited [1]
    out = _ensure_marker_citations(text, enriched, sources)
    idxs = sorted(c.index for c in out)
    assert idxs == [1, 2, 3]                  # every marker now has an entry
    assert all(c.chunkId for c in out)        # each links to a source chunk


def test_ensure_marker_citations_noop_without_sources():
    from src.services.chat.agents.deep_tutor import _ensure_marker_citations
    assert _ensure_marker_citations("text [1]", [], []) == []


def test_applications_real_cases_contract():
    # §11 Block E: Applications must cite REAL specific cases, not domain labels
    assert "applications" in INSTR
    assert "real, specific cases" in INSTR
    assert "a bare domain label" in INSTR
    assert "no concrete applied case" in INSTR


def test_aspect_heading_renamed_to_applications():
    from src.services.chat.prompts.deep_tutor import ASPECT_HEADINGS

    assert ASPECT_HEADINGS["applications"] == "Applications"
    assert "trade_offs" not in ASPECT_HEADINGS
    assert "Trade-offs and caveats" not in ASPECT_HEADINGS.values()


def test_example_intuition_merged_field_contract():
    # Block C: intuition + examples merged into one three-move field
    from src.services.chat.prompts.deep_tutor import ASPECT_HEADINGS

    assert ASPECT_HEADINGS["example_intuition"] == "Example & Intuition"
    assert "intuition" not in ASPECT_HEADINGS
    assert "examples" not in ASPECT_HEADINGS
    assert "describe three cases" in INSTR
    assert "analyse the three" in INSTR
    assert "the intuition here is that" in INSTR


# --- #8 example relevance audit ----------------------------------------
def test_examples_self_audit_note_required():
    assert "relevance audit" in INSTR
    assert "why these cases fit" in INSTR


def test_example_relevance_scorer():
    from src.services.chat.agents.deep_tutor import _score_example_relevance

    related = {
        "definition": "A sampling distribution describes the variation of an estimator across samples.",
        "formal_statement": "The estimator variance shrinks with sample size n.",
        "example_intuition": "Drawing samples of size n, the estimator variance shrinks as the sampling distribution narrows. The intuition here is that more data sharpens the estimator.",
    }
    disjoint = {
        "definition": "A sampling distribution describes estimator variation.",
        "formal_statement": "Variance shrinks with sample size.",
        "example_intuition": "Yesterday the weather forecast predicted rainfall amounts across coastal regions.",
    }
    high = _score_example_relevance(related)
    low = _score_example_relevance(disjoint)
    assert 0.0 <= low < high <= 1.0
    assert high >= 0.4
    # empty example -> 0.0
    assert _score_example_relevance({"example_intuition": "", "definition": "x y z"}) == 0.0


# --- #9 image: connect + vision explain --------------------------------
def test_figures_prompt_requires_conceptual_link():
    assert "connect the figure to what was just taught" in INSTR
    assert "what the figure demonstrates about the definition" in INSTR


def test_build_vision_explanations_off_by_default():
    import asyncio

    from src.services.chat.agents.deep_tutor import build_vision_explanations

    class _Fig:
        url = "/api/figures?path=/x.png"

    # env flag unset in tests -> no vision calls, empty map
    out = asyncio.run(build_vision_explanations({"definition": "d"}, [_Fig()]))
    assert out == {}


def test_convert_uses_vision_explanation_when_provided():
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import FigureRef

    fig = FigureRef(
        ref="r1", book="Book", chapter="ch1",
        caption="A scatter of residuals", url="u1", aspect_hint="example_intuition",
    )
    aspects = {
        "tldr": "intro", "definition": "residual plot definition",
        "formal_statement": "",
        "example_intuition": "Here residuals scatter around zero.",
        "applications": "", "further_reading": "",
    }
    ans = _convert_to_tutor_answer(
        None, aspects, [], approved_figures=[fig],
        vision_explanations={"u1": "VISION: the points hug the zero line, showing homoscedasticity."},
    )
    assert "VISION: the points hug the zero line" in ans.text
    assert "![A scatter of residuals](u1)" in ans.text


# --- #7v verbatim blockquote check -------------------------------------
def _src(chunk: str):
    from src.services.chat.schemas import Source

    return Source(
        rank=1, book="b", chapter="c", section="s", title="t",
        excerpt=chunk[:80], score=0.9, chunkId="cid", chunk=chunk,
    )


def test_verbatim_match_none_without_blockquote():
    from src.services.chat.agents.deep_tutor import _verbatim_blockquote_match

    assert _verbatim_blockquote_match("Plain prose, no quote.", [_src("anything")]) is None


def test_verbatim_match_detects_substring_and_mismatch():
    from src.services.chat.agents.deep_tutor import _verbatim_blockquote_match

    theorem = "The estimator is unbiased if its expectation equals the parameter."
    formal = f"Stated formally:\n\n> {theorem} [1]\n"
    # exact source -> 1.0
    assert _verbatim_blockquote_match(formal, [_src("Chapter 3. " + theorem)]) == 1.0
    # unrelated source -> low recall, well under the 0.85 warn line
    low = _verbatim_blockquote_match(formal, [_src("Completely different text about weather patterns.")])
    assert low is not None and low < 0.85


# --- #8e embedding relevance fallback ----------------------------------
def test_embed_relevance_none_on_empty():
    import asyncio

    from src.services.chat.agents.deep_tutor import _embed_relevance

    # empty example -> None (no network call), so caller uses lexical
    assert asyncio.run(_embed_relevance({"example_intuition": "", "definition": "d"})) is None


def test_convert_uses_relevance_override():
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer

    aspects = {k: "" for k in (
        "tldr", "definition", "formal_statement", "example_intuition",
        "applications", "further_reading")}
    aspects["definition"] = "some concept"
    aspects["example_intuition"] = "an example using the concept"
    ans = _convert_to_tutor_answer(None, aspects, [], example_relevance_override=0.91)
    assert ans.quality["example_relevance"] == 0.91


# --- Phase-1 token-budget regression guard ---------------------------------
# Soft regression guard: ceiling sits deliberately above the current ~18.7k size
# to catch runaway bloat while leaving comfortable room for intentional additions.
# Raise it when you genuinely add new rules; lower it after a prompt-diet pass.
_PROMPT_BUDGET_CEILING = 20_500


def test_deep_tutor_instructions_within_token_budget():
    """DEEP_TUTOR_INSTRUCTIONS must not grow beyond the post-diet ceiling."""
    n = len(DEEP_TUTOR_INSTRUCTIONS)
    assert n < _PROMPT_BUDGET_CEILING, (
        f"DEEP_TUTOR_INSTRUCTIONS is {n} chars, exceeds budget {_PROMPT_BUDGET_CEILING}. "
        "Remove duplicate rules before adding new ones."
    )


def test_definition_states_component_formulas():
    assert "defining formula" in INSTR


def test_definition_prefers_verbatim_then_reconstructs_equations():
    assert "copy it verbatim" in INSTR
    assert "reconstruct" in INSTR


def test_author_worker_preserves_equations():
    from src.services.chat.prompts.deep_tutor import AUTHOR_WORKER_PROMPT
    p = AUTHOR_WORKER_PROMPT.lower()
    assert "preserve equations" in p
    assert "verbatim" in p


def test_recovered_equations_rule_present():
    assert "<recovered_equations>" in INSTR or "recovered_equations" in INSTR
    assert "verbatim" in INSTR


def test_deep_tutor_inline_delimiter_rule_present():
    from src.services.chat.prompts.deep_tutor import DEEP_TUTOR_INSTRUCTIONS as INSTR
    low = INSTR.lower()
    assert "wrap" in low and ("$…$" in INSTR or "$...$" in INSTR or "inline" in low)
    # bans bare commands / dangling citation after display block
    assert "bare" in low or "undelimited" in low
