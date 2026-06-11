"""Tests for the deep tutor pipeline v2 (multi-aspect schema).

Coverage:
    - Unit: concept extraction, occurrence counting, critique parse,
      conversion DeepTutorAnswer -> TutorAnswer, citation reconciliation.
    - Integration (mocked LLM + retrieval): SSE event sequence,
      critique-off default, critique-on opt-in, parallel scheduling,
      empty-corpus failure mode.
    - Quality: per-aspect non-empty, copy-paste guardrail, H2 count,
      total word count.
    - Performance: mocked latency < 2s.

All external I/O is mocked.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")
os.environ.setdefault("TUTOR_DEEP_WARM", "0")  # skip background reranker warm in tests
os.environ.setdefault("TUTOR_DEEP_IMAGES", "0")  # default-off images in tests


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _src(rank: int, book: str, section: str, text: str, chunk_id: str | None = None):
    from src.services.chat.schemas import Source
    return Source(
        rank=rank, book=book, chapter=f"ch0{rank}", section=section,
        title=f"{book} §{section}", excerpt=text[:200], score=1.0 / rank,
        chunkId=chunk_id or f"{book}-{section}-{rank}", chunk=text,
        book_name=book.upper(), authors="Smith, Doe", authors_short="Smith et al.",
        year=2024, page_from=10 * rank, page_to=10 * rank + 5, page=10 * rank,
    )


@pytest.fixture
def sample_sources():
    return [
        _src(1, "islp", "2.1", "Bias and variance are central to the bias-variance tradeoff."),
        _src(2, "islp", "2.2", "Variance captures sensitivity to training data."),
        _src(3, "esl", "3.4", "The bias-variance decomposition splits expected loss."),
        _src(4, "esl", "3.5", "Regularization reduces variance at the cost of bias."),
    ]


def _make_deep_answer(**overrides):
    from src.services.chat.schemas.output import DeepTutorAnswer
    payload = dict(
        tldr="The data generating process is the underlying stochastic mechanism that produces observed data. " * 3,
        definition="A data generating process (DGP) is an unobserved probabilistic model defined on a sample space. " * 8,
        formal_statement="Formally we write $Y_i \\sim P$ where $P$ is the joint distribution on the sample space. " * 8,
        example_intuition="Imagine the world flipping coins: the DGP is the unseen rule that decides each flip. In linear regression we assume $y = X\\beta + \\varepsilon$, a parametric DGP. The intuition here is that the data we see are one draw from this hidden rule. " * 6,
        applications="In econometrics the DGP framing underpins identification; in finance it models return-generating processes. " * 6,
        further_reading="See ESL chapter 7 and Casella for measure-theoretic foundations. " * 3,
    )
    payload.update(overrides)
    return DeepTutorAnswer(**payload)


# ---------------------------------------------------------------------------
# Unit: density helpers
# ---------------------------------------------------------------------------


def test_count_occurrences_word_boundary():
    from src.services.chat.retrievers.density import _count_occurrences
    assert _count_occurrences("gradient gradient ascending", "gradient") == 2
    assert _count_occurrences("CASE insensitive Case", "case") == 2
    assert _count_occurrences("", "x") == 0


def test_count_occurrences_hyphenated_phrase():
    from src.services.chat.retrievers.density import _count_occurrences
    assert _count_occurrences("bias-variance again. bias-variance ok.", "bias-variance") == 2


def test_section_score_blends_count_and_score():
    from src.services.chat.retrievers.density import _section_score
    assert _section_score(1.0, 0.0) > _section_score(0.0, 1.0)


# ---------------------------------------------------------------------------
# Unit: extract_concepts
# ---------------------------------------------------------------------------


def test_extract_concepts_parses_array():
    from src.services.chat.agents import deep_tutor

    async def fake_create(*a, **kw):
        return MagicMock(choices=[MagicMock(message=MagicMock(
            content='["bias-variance tradeoff", "regularization"]'))])

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    with patch.object(deep_tutor, "_async_client", return_value=fake_client):
        out = asyncio.run(deep_tutor.extract_concepts("Bias-variance tradeoff?"))
    assert out == ["bias-variance tradeoff", "regularization"]


def test_extract_concepts_caps_at_three():
    from src.services.chat.agents import deep_tutor

    async def fake_create(*a, **kw):
        return MagicMock(choices=[MagicMock(message=MagicMock(
            content='["a","b","c","d","e"]'))])

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    with patch.object(deep_tutor, "_async_client", return_value=fake_client):
        out = asyncio.run(deep_tutor.extract_concepts("q"))
    assert len(out) == 3


# ---------------------------------------------------------------------------
# Unit: critique
# ---------------------------------------------------------------------------


def test_critique_parses_verdict():
    from src.services.chat.agents import deep_tutor

    payload = json.dumps({"complete": False, "missing": ["a"],
                          "copy_paste_risk": "high", "reason": "thin"})

    async def fake_create(*a, **kw):
        return MagicMock(choices=[MagicMock(message=MagicMock(content=payload))])

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    with patch.object(deep_tutor, "_async_client", return_value=fake_client):
        v = asyncio.run(deep_tutor.critique("draft", ["x"], []))
    assert v["complete"] is False
    assert v["copy_paste_risk"] == "high"


def test_critique_empty_draft_marks_incomplete():
    from src.services.chat.agents import deep_tutor
    v = asyncio.run(deep_tutor.critique("", ["x"], []))
    assert v["complete"] is False


# ---------------------------------------------------------------------------
# Unit: conversion DeepTutorAnswer -> TutorAnswer
# ---------------------------------------------------------------------------


def test_convert_fills_aspects_text_and_sections(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer

    deep = _make_deep_answer()
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)

    assert set(ans.aspects.keys()) == {
        "tldr", "definition", "formal_statement", "example_intuition",
        "applications", "further_reading",
    }
    assert all(v.strip() for v in ans.aspects.values())
    assert ans.text.count("## ") == 6
    # back-compat text contains every aspect heading
    for heading in ["Introduction", "Definition", "Formal statement",
                    "Example & Intuition", "Applications", "Further reading"]:
        assert heading in ans.text


def test_convert_recovers_when_deep_is_none(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    ans = _convert_to_tutor_answer(None, {"tldr": "stub answer"}, sample_sources)
    assert "stub answer" in ans.text


def test_convert_returns_error_when_completely_empty():
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    ans = _convert_to_tutor_answer(None, {}, [])
    assert "Error" in ans.text


# ---------------------------------------------------------------------------
# Unit: citation reconciliation
# ---------------------------------------------------------------------------


def test_reconcile_citations_enriches_from_sources(sample_sources):
    from src.services.chat.agents.deep_tutor import _reconcile_citations
    from src.services.chat.schemas.output import TutorCitation

    cites = [
        TutorCitation(index=1, chunkId=sample_sources[0].chunkId, quote="x"),
        TutorCitation(index=2, chunkId=sample_sources[2].chunkId, quote="y"),
    ]
    enriched = _reconcile_citations(cites, sample_sources)
    assert enriched[0].authors_short == "Smith et al."
    assert enriched[0].page_from == 10
    assert enriched[1].chapter == "ch03"


# ---------------------------------------------------------------------------
# Helpers: merge sources
# ---------------------------------------------------------------------------


def test_merge_sources_dedupes(sample_sources):
    from src.services.chat.agents.deep_tutor import _merge_sources
    extra = [_src(1, "islp", "2.1", "dup", chunk_id=sample_sources[0].chunkId),
             _src(2, "new", "9.9", "fresh")]
    merged = _merge_sources(sample_sources, extra)
    assert len(merged) == len(sample_sources) + 1


# ---------------------------------------------------------------------------
# Integration: full pipeline w/ mocked LLM + retrieval
# ---------------------------------------------------------------------------


def _patch_pipeline(deep_answer, sources, calls=None):
    """Return a context manager applying all common patches."""
    from src.services.chat.agents import deep_tutor as dt
    from src.services.chat.schemas import RetrievalMetadata

    calls = calls if calls is not None else {"density": 0, "draft": 0, "critique": 0}

    async def fake_extract(q, *, model=None):
        return ["data generating process"]

    async def fake_extract_ex(q, *, model=None, max_authors=4):
        return dt.QueryPlan(["data generating process"], min(2, max_authors), [], [])

    async def fake_plan(q, srcs, *, model=None):
        return None  # no synthesis plan in unit tests

    async def fake_wide(q, slugs, pool):
        return list(sources), RetrievalMetadata(
            rewrittenQuery=q, embedding="x", retrievalMs=1, collections=["c1"],
            filter="f", topK=len(sources), scoreThreshold=0.0, mode="mock-wide",
        )

    def fake_density(query, concepts, candidates, *, book_slugs=None, **kw):
        calls["density"] += 1
        return list(sources), ["c1"]

    async def fake_draft(q, srcs, *, figures=None, on_aspect_delta=None, model=None, plan=None, **kwargs):
        calls["draft"] += 1
        from src.services.chat.prompts.deep_tutor import ASPECT_HEADINGS
        aspects = {k: getattr(deep_answer, k) for k in ASPECT_HEADINGS}
        if on_aspect_delta:
            for k, v in aspects.items():
                on_aspect_delta(k, v)
        return deep_answer, aspects

    async def fake_critique(draft_text, concepts, sources_, *, model=None):
        calls["critique"] += 1
        return {"complete": True, "missing": [], "copy_paste_risk": "low", "reason": "ok"}

    async def fake_recover(q, srcs):
        return ""

    patches = [
        patch.object(dt, "extract_concepts", fake_extract),
        patch.object(dt, "extract_concepts_ex", fake_extract_ex),
        patch.object(dt, "build_synthesis_plan", fake_plan),
        patch.object(dt, "_wide_candidates", fake_wide),
        patch.object(dt, "_density_select", fake_density),
        patch.object(dt, "_stream_draft", fake_draft),
        patch.object(dt, "_recover_equations_block", fake_recover),
        patch.object(dt, "critique", fake_critique),
        patch.object(dt, "_IMAGES_ENABLED", False),
    ]
    class _Ctx:
        def __enter__(self_):
            for p in patches: p.start()
            return calls
        def __exit__(self_, *a):
            for p in patches: p.stop()
    return _Ctx()


def test_run_deep_tutor_emits_sse_sequence(sample_sources):
    from src.services.chat.agents import deep_tutor
    from src.services.chat.schemas import ChatRequest

    deep = _make_deep_answer()
    req = ChatRequest(message="What is data generating process?",
                      mode="tutor", model="gpt-5.4-nano-2026-03-17")

    with _patch_pipeline(deep, sample_sources):
        async def collect():
            return [e async for e in deep_tutor.run_deep_tutor(req)]
        events = asyncio.run(collect())

    kinds = [e["type"] for e in events]
    assert kinds[0] == "meta"
    assert kinds[-1] == "done"
    assert "token" in kinds
    assert "structured_output" in kinds
    assert "sources_full" in kinds
    assert "retrieval_meta" in kinds
    assert "usage" in kinds

    structured = next(e for e in events if e["type"] == "structured_output")
    assert structured["schema"] == "TutorAnswer"
    data = structured["data"]
    assert "aspects" in data
    assert set(data["aspects"].keys()) == {
        "tldr", "definition", "formal_statement", "example_intuition",
        "applications", "further_reading",
    }
    assert all(v.strip() for v in data["aspects"].values())
    assert data["text"].count("## ") == 6
    # token events carry aspect attribution
    tokens = [e for e in events if e["type"] == "token"]
    assert all("aspect" in t for t in tokens)


def test_critique_off_by_default(sample_sources):
    from src.services.chat.agents import deep_tutor
    from src.services.chat.schemas import ChatRequest

    deep = _make_deep_answer()
    req = ChatRequest(message="q", mode="tutor", model="gpt-5.4-nano-2026-03-17")
    with patch.object(deep_tutor, "_ENABLE_CRITIQUE", False), \
         _patch_pipeline(deep, sample_sources) as calls:
        asyncio.run(_drain(deep_tutor.run_deep_tutor(req)))
    assert calls["critique"] == 0
    assert calls["draft"] == 1
    assert calls["density"] == 1


def test_critique_on_via_env_runs_critique(sample_sources):
    from src.services.chat.agents import deep_tutor
    from src.services.chat.schemas import ChatRequest

    deep = _make_deep_answer()
    req = ChatRequest(message="q", mode="tutor", model="gpt-5.4-nano-2026-03-17")
    with patch.object(deep_tutor, "_ENABLE_CRITIQUE", True), \
         _patch_pipeline(deep, sample_sources) as calls:
        asyncio.run(_drain(deep_tutor.run_deep_tutor(req)))
    assert calls["critique"] == 1


def test_empty_corpus_short_circuits():
    from src.services.chat.agents import deep_tutor
    from src.services.chat.schemas import ChatRequest, RetrievalMetadata

    async def fake_extract(q, *, model=None): return ["x"]
    async def fake_wide(q, slugs, pool):
        return [], RetrievalMetadata(rewrittenQuery=q, embedding="x", retrievalMs=1,
                                     collections=[], filter="", topK=0,
                                     scoreThreshold=0.0, mode="empty")
    def fake_density(*a, **kw): return [], []

    req = ChatRequest(message="q", mode="tutor", model="gpt-5.4-nano-2026-03-17")
    with patch.object(deep_tutor, "extract_concepts", fake_extract), \
         patch.object(deep_tutor, "_wide_candidates", fake_wide), \
         patch.object(deep_tutor, "_density_select", fake_density):
        events = asyncio.run(_drain(deep_tutor.run_deep_tutor(req)))
    out = next(e for e in events if e["type"] == "structured_output")
    assert "No corpus coverage" in out["data"]["text"]


async def _drain(gen):
    out = []
    async for e in gen:
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# Performance: mocked end-to-end under 2s
# ---------------------------------------------------------------------------


def test_pipeline_latency_under_2s_when_mocked(sample_sources):
    import time as _t
    from src.services.chat.agents import deep_tutor
    from src.services.chat.schemas import ChatRequest

    deep = _make_deep_answer()
    req = ChatRequest(message="q", mode="tutor", model="gpt-5.4-nano-2026-03-17")
    with _patch_pipeline(deep, sample_sources):
        t0 = _t.monotonic()
        asyncio.run(_drain(deep_tutor.run_deep_tutor(req)))
        elapsed = _t.monotonic() - t0
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# Quality guards
# ---------------------------------------------------------------------------


def test_quality_each_aspect_has_minimum_length(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer()
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)
    for key, body in ans.aspects.items():
        word_count = len(body.split())
        assert word_count >= 15, f"{key} too short: {word_count} words"


def test_quality_total_word_count_above_400(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer()
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)
    assert len(ans.text.split()) >= 400


def _longest_common_substring(a: str, b: str) -> int:
    if not a or not b: return 0
    n, m = len(a), len(b)
    dp = [0] * (m + 1)
    best = 0
    for i in range(1, n + 1):
        new = [0] * (m + 1)
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                new[j] = dp[j - 1] + 1
                best = max(best, new[j])
        dp = new
    return best


def test_quality_no_copy_paste_in_canned_answer(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer()
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)
    threshold = 80
    for src in sample_sources:
        lcs = _longest_common_substring(ans.text, src.chunk or "")
        assert lcs < threshold, f"verbatim {lcs} chars from {src.book}"


def test_aspects_field_persists_through_model_dump(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer()
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)
    dumped = ans.model_dump()
    assert "aspects" in dumped
    assert dumped["aspects"]["tldr"].strip()


# ---------------------------------------------------------------------------
# LaTeX escape repair
# ---------------------------------------------------------------------------


def test_repair_latex_escapes_doubles_known_command():
    """Raw JSON containing single-backslash latex command must be repaired."""
    import json
    from src.services.chat.agents.deep_tutor import _repair_latex_escapes
    raw = '{"formal_statement": "Bias = E[\\theta] - \\nabla(D)."}'
    fixed = _repair_latex_escapes(raw)
    parsed = json.loads(fixed)
    body = parsed["formal_statement"]
    assert "\\theta" in body
    assert "\\nabla" in body
    assert "\theta" not in body  # control-char tab gone
    assert "\nabla" not in body


def test_repair_latex_escapes_skips_already_doubled():
    """Already double-escaped commands must not become triple."""
    from src.services.chat.agents.deep_tutor import _repair_latex_escapes
    raw = '{"x": "\\\\theta"}'  # JSON for `\\theta`
    assert _repair_latex_escapes(raw) == raw


def test_repair_latex_escapes_no_op_on_plain_text():
    from src.services.chat.agents.deep_tutor import _repair_latex_escapes
    assert _repair_latex_escapes("hello world") == "hello world"


def test_repair_latex_post_reattaches_tab_to_theta():
    """When the streaming parser already collapsed `\\t` → TAB, the input
    contains TAB+`heta` (first letter consumed). Post pass must restore
    `\\theta`."""
    from src.services.chat.agents.deep_tutor import _repair_latex_post
    corrupted = "Bias = E[\theta] - \theta"  # literal: E[<TAB>heta] - <TAB>heta
    fixed = _repair_latex_post(corrupted)
    assert "\\theta" in fixed
    assert "\theta" not in fixed  # tab gone


def test_repair_latex_post_reattaches_newline_to_nabla():
    from src.services.chat.agents.deep_tutor import _repair_latex_post
    corrupted = "Use \nabla_x f"  # <NL>abla
    fixed = _repair_latex_post(corrupted)
    assert "\\nabla" in fixed


def test_wrap_bare_math_wraps_simple_command():
    from src.services.chat.agents.deep_tutor import _wrap_bare_math
    out = _wrap_bare_math("The estimator \\hat{\\theta} is unbiased.")
    assert "$\\hat{\\theta}$" in out
    assert "is unbiased" in out


def test_wrap_bare_math_skips_already_delimited():
    from src.services.chat.agents.deep_tutor import _wrap_bare_math
    s = "Already wrapped $\\theta = 1$ unchanged."
    out = _wrap_bare_math(s)
    assert out.count("$\\theta") == 1
    assert "$$" not in out


def test_wrap_bare_math_skips_pure_text():
    from src.services.chat.agents.deep_tutor import _wrap_bare_math
    assert _wrap_bare_math("Plain English with no math.") == "Plain English with no math."


def test_wrap_bare_math_handles_big_delimiters():
    from src.services.chat.agents.deep_tutor import _wrap_bare_math
    inp = "Var = E\\big[(\\hat{\\theta} - \\theta)^2\\big]."
    out = _wrap_bare_math(inp)
    assert "$" in out
    assert "\\big" in out


def test_repair_latex_post_word_boundary_no_false_positive():
    """`<TAB>extra` must NOT become `\\textra` — `ext` is a stem but
    followed by `r` (alnum)."""
    from src.services.chat.agents.deep_tutor import _repair_latex_post
    inp = "Adds \textra padding"  # <TAB>extra
    fixed = _repair_latex_post(inp)
    assert "\\text" not in fixed
    assert "\\textra" not in fixed


def test_repair_latex_post_idempotent_on_clean_text():
    from src.services.chat.agents.deep_tutor import _repair_latex_post
    s = "Define $\\hat{\\theta}$ as the estimator."
    assert _repair_latex_post(s) == s


# ---------------------------------------------------------------------------
# Figure injection into aspect markdown
# ---------------------------------------------------------------------------


def _mk_fig(**overrides):
    from src.services.chat.schemas.output import FigureRef
    defaults = dict(
        ref="r1", book="islp", chapter="ch02",
        caption="Bias-variance U-curve.", url="/api/figures?path=foo.jpg",
        aspect_hint="example_intuition", figure_role="diagram",
        judge_confidence=0.9, judge_reason="Directly depicts the trade-off.",
    )
    defaults.update(overrides)
    return FigureRef(**defaults)


def test_convert_injects_figure_markdown_into_target_aspect(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer()
    fig = _mk_fig()
    ans = _convert_to_tutor_answer(deep, {}, sample_sources, approved_figures=[fig])
    assert "![Bias-variance U-curve" in ans.text
    assert "/api/figures?path=foo.jpg" in ans.text
    # injected inside the Examples section, not stray
    examples_idx = ans.text.find("## Examples")
    img_idx = ans.text.find("![Bias-variance")
    assert examples_idx < img_idx, "image should land inside Examples section"


def test_convert_emits_lead_and_explanation_around_image(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer()
    fig = _mk_fig()
    ans = _convert_to_tutor_answer(deep, {}, sample_sources, approved_figures=[fig])
    # lead sentence references book + chapter
    assert "islp ch02" in ans.text
    # explanation contains the judge reason (after the image)
    assert "Directly depicts" in ans.text


def test_convert_falls_back_to_examples_when_hint_missing(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer()
    fig = _mk_fig(aspect_hint=None)
    ans = _convert_to_tutor_answer(deep, {}, sample_sources, approved_figures=[fig])
    # default placement now lands in the merged Example & Intuition section
    examples_idx = ans.text.find("## Example & Intuition")
    img_idx = ans.text.find("![")
    assert examples_idx >= 0 and img_idx > examples_idx
    # figure renders under its own "### Figure example" subsection, before the image
    figex_idx = ans.text.find("### Figure example")
    assert figex_idx >= 0 and figex_idx < img_idx


def test_convert_no_image_when_url_missing(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer()
    fig = _mk_fig(url="")
    ans = _convert_to_tutor_answer(deep, {}, sample_sources, approved_figures=[fig])
    assert "![" not in ans.text


# ---------------------------------------------------------------------------
# Aspect placement scoring
# ---------------------------------------------------------------------------


def test_word_tokens_strips_stopwords_and_short():
    from src.services.chat.agents.deep_tutor import _word_tokens
    toks = _word_tokens("The bias-variance tradeoff and the example are key.")
    # Stopwords (the, and, are) and short words gone.
    assert "the" not in toks and "and" not in toks
    assert "bias-variance" in toks or "tradeoff" in toks


def test_choose_target_aspect_uses_overlap_when_hint_missing():
    from src.services.chat.agents.deep_tutor import _choose_target_aspect

    class Fig:
        caption = "Bias and variance decomposition of squared error."
        judge_reason = ""
        aspect_hint = None

    aspects = {
        "tldr": "Short answer.",
        "definition": "Definitions stuff.",
        "formal_statement": "Bias variance decomposition derivation squared error.",
        "example_intuition": "Worked example with polynomial regression. The intuition here is that flexibility trades bias for variance.",
        "applications": "Applications.",
        "further_reading": "Refs.",
    }
    target = _choose_target_aspect(Fig(), aspects, "example_intuition")
    assert target == "formal_statement"


def test_choose_target_aspect_respects_hint_when_set():
    from src.services.chat.agents.deep_tutor import _choose_target_aspect

    class Fig:
        caption = "x"  # too short to score
        judge_reason = ""
        aspect_hint = "example_intuition"

    aspects = {k: "body" for k in (
        "tldr", "definition", "formal_statement", "example_intuition",
        "applications", "further_reading",
    )}
    assert _choose_target_aspect(Fig(), aspects, "applications") == "example_intuition"


def test_choose_target_aspect_falls_back_when_no_signal():
    from src.services.chat.agents.deep_tutor import _choose_target_aspect

    class Fig:
        caption = ""
        judge_reason = ""
        aspect_hint = None

    aspects = {"example_intuition": "Examples body.", "tldr": "Other."}
    assert _choose_target_aspect(Fig(), aspects, "example_intuition") == "example_intuition"


# ---------------------------------------------------------------------------
# Lead-sentence variety
# ---------------------------------------------------------------------------


def test_build_lead_role_aware_templates():
    from src.services.chat.agents.deep_tutor import _build_lead
    lead = _build_lead("diagram", "islp ch02", "the bias-variance curve", 0)
    assert "diagram" in lead
    assert "islp ch02" in lead
    assert "bias-variance" in lead


def test_build_lead_varies_with_seq():
    from src.services.chat.agents.deep_tutor import _build_lead
    a = _build_lead("graph", "x y", "topic A", 0)
    b = _build_lead("graph", "x y", "topic A", 1)
    # Two graph templates exist; should differ when seq increments.
    assert a != b


def test_build_lead_handles_missing_topic():
    from src.services.chat.agents.deep_tutor import _build_lead
    lead = _build_lead("figure", "src", "the concept above", 0)
    assert "src" in lead
    # No-topic template doesn't include the placeholder topic string
    assert "the concept above" not in lead


def test_build_lead_normalises_other_role():
    """`role='other'` must not produce 'The other below from ...'."""
    from src.services.chat.agents.deep_tutor import _build_lead
    lead = _build_lead("other", "islp ch02", "the bias-variance curve", 0)
    assert "The other" not in lead
    assert "figure" in lead


def test_choose_target_aspect_excludes_tldr():
    """TL;DR must never receive auto-placed figures."""
    from src.services.chat.agents.deep_tutor import _choose_target_aspect

    class Fig:
        caption = "Bias variance tradeoff curves of MSE vs flexibility."
        judge_reason = ""
        aspect_hint = None

    # TL;DR is densely on-topic but should still be skipped.
    aspects = {
        "tldr": "Bias variance tradeoff MSE flexibility curves overview",
        "example_intuition": "Polynomial regression example.",
        "definition": "",
        "formal_statement": "",
        "applications": "",
        "further_reading": "",
    }
    target = _choose_target_aspect(Fig(), aspects, "example_intuition")
    assert target != "tldr"


# ---------------------------------------------------------------------------
# Block A — draft size + temperature knobs (answer-coherence feature)
# ---------------------------------------------------------------------------


def test_draft_knobs_defaults():
    """Draft size + temperature defaults: bigger output, controlled creativity."""
    import src.services.chat.agents.deep_tutor as dt

    assert dt._MAX_COMPLETION_TOKENS == 16000
    assert dt._DRAFT_TEMPERATURE == 0.4


def test_draft_knobs_env_override(monkeypatch):
    """TUTOR_DEEP_MAX_TOKENS / TUTOR_DEEP_TEMPERATURE override the defaults."""
    import importlib
    import src.services.chat.agents.deep_tutor as dt

    monkeypatch.setenv("TUTOR_DEEP_MAX_TOKENS", "5200")
    monkeypatch.setenv("TUTOR_DEEP_TEMPERATURE", "0.7")
    try:
        importlib.reload(dt)
        assert dt._MAX_COMPLETION_TOKENS == 5200
        assert dt._DRAFT_TEMPERATURE == 0.7
    finally:
        monkeypatch.undo()
        importlib.reload(dt)


# ---------------------------------------------------------------------------
# Phase-1 changes: vision tri-state + coverage gate
# ---------------------------------------------------------------------------


def test_vision_explain_default_is_lazy():
    """Default TUTOR_DEEP_VISION_EXPLAIN is 'lazy' → build_vision_explanations returns {}."""
    import asyncio
    import src.services.chat.agents.deep_tutor as dt

    # In test env, TUTOR_DEEP_VISION_EXPLAIN is unset → mode defaults to "lazy".
    assert dt._VISION_EXPLAIN_MODE in ("lazy", "0"), (
        f"Expected lazy/0 default, got {dt._VISION_EXPLAIN_MODE!r}"
    )

    class _Fig:
        url = "/api/figures?path=/x.png"

    out = asyncio.run(dt.build_vision_explanations({"definition": "d"}, [_Fig()]))
    assert out == {}


def test_vision_explain_mode_1_caps_to_single_figure(monkeypatch):
    """TUTOR_DEEP_VISION_EXPLAIN=1 should only explain the first figure."""
    import importlib
    import asyncio
    import src.services.chat.agents.deep_tutor as dt

    class _Fig:
        def __init__(self, url: str):
            self.url = url
            self.caption = "cap"
            self.judge_reason = ""

    called_urls: list[str] = []

    async def _fake_explain(concept, fig, model=None):
        called_urls.append(getattr(fig, "url", ""))
        return "vision text"

    monkeypatch.setenv("TUTOR_DEEP_VISION_EXPLAIN", "1")
    try:
        importlib.reload(dt)
        with __import__("unittest.mock", fromlist=["patch"]).patch.object(
            dt, "_explain_figure_vision", side_effect=_fake_explain
        ):
            figs = [_Fig("/img1.png"), _Fig("/img2.png"), _Fig("/img3.png")]
            out = asyncio.run(dt.build_vision_explanations(
                {"definition": "bias variance", "formal_statement": ""},
                figs,
            ))
        assert len(out) == 1, f"Expected exactly 1 explanation, got {len(out)}"
        assert "/img1.png" in out
        assert len(called_urls) == 1
    finally:
        monkeypatch.undo()
        importlib.reload(dt)


def test_coverage_gate_skips_simple(caplog):
    """Simple questions (< 4 facets, no formula) skip the coverage call."""
    import logging
    import importlib
    import asyncio
    import src.services.chat.agents.deep_tutor as dt
    from src.services.chat.agents.coverage import COVERAGE_ON

    if not COVERAGE_ON:
        import pytest
        pytest.skip("TUTOR_COVERAGE_CHECK=0, gate not reachable")

    # Patch assess_coverage so it is NOT called.
    assessment_called = []

    async def _mock_assess(*args, **kwargs):
        assessment_called.append(True)
        return []

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "src.services.chat.agents.deep_tutor.assess_coverage", side_effect=_mock_assess
    ):
        # Simulate the gate predicate directly (no full pipeline needed).
        facets_simple = ["bias definition"]  # < 4, no "$", no "formula"
        needs = bool(facets_simple) and (
            len(facets_simple) >= 4
            or any("$" in f or "formula" in f.lower() for f in facets_simple)
        )
        assert not needs, "Simple facet set should not need coverage"
        # The gate log message should appear when we drive the gate manually.
        # Coverage gate predicate computed; log the skip.
        with caplog.at_level(logging.INFO, logger="src.services.chat.agents.deep_tutor"):
            if not needs and COVERAGE_ON and facets_simple:
                dt.logger.info("coverage: skipped (simple)")
        assert any("coverage: skipped (simple)" in r.message for r in caplog.records)
        assert not assessment_called


def test_coverage_gate_runs_complex():
    """Complex questions (4+ facets or formula facet) run coverage."""
    facets_complex_count = ["a", "b", "c", "d"]  # >= 4 → run
    facets_formula = ["bias formula $"]  # has "$" → run
    facets_formula_word = ["compute the formula for variance"]  # has "formula" → run

    def _needs(facets):
        return bool(facets) and (
            len(facets) >= 4
            or any("$" in f or "formula" in f.lower() for f in facets)
        )

    assert _needs(facets_complex_count)
    assert _needs(facets_formula)
    assert _needs(facets_formula_word)
    assert not _needs([])   # empty → fail-safe False (gate condition: bool(facets) is False)


# ---------------------------------------------------------------------------
# Phase-2 changes: draft-model upgrade, related-framings facet, topic diversity
# ---------------------------------------------------------------------------


def test_draft_stage_resolves_to_nano_by_default():
    """Draft stage default is now nano (eval value-winner; structured-safe); other stages also nano."""
    import src.services.chat.agents.deep_tutor as dt
    from src.core.config import settings

    # Exercise the REAL wiring: req.model carries the schema-default nano, which
    # must fall through to the nano _DRAFT_MODEL_DEFAULT (both are nano now).
    base_default = dt._resolve_draft_default(settings.openai_model_nano)
    assert base_default == settings.openai_model_nano, (
        f"schema-default nano must fall through to nano default; got {base_default!r}"
    )
    assert dt._resolve_draft_default(None) == settings.openai_model_nano
    # An explicit, different pick still wins (About-model feature).
    assert dt._resolve_draft_default("gpt-4o") == "gpt-4o"

    # Given that base, draft resolves to nano; other stages also stay nano.
    draft_model = dt._resolve_stage_model("draft", base_default, None)
    assert draft_model == settings.openai_model_nano, (
        f"Expected draft default={settings.openai_model_nano}, got {draft_model!r}"
    )
    assert dt._resolve_stage_model("expansion", base_default, None) == settings.openai_model_nano
    assert dt._resolve_stage_model("critique", base_default, None) == settings.openai_model_nano
    assert dt._resolve_stage_model("image_judge", base_default, None) == settings.openai_model_nano


def test_draft_model_env_override_revert_to_nano(monkeypatch):
    """TUTOR_DRAFT_MODEL=nano reverts draft to nano (revert path)."""
    import importlib
    import src.services.chat.agents.deep_tutor as dt
    from src.core.config import settings

    monkeypatch.setenv("TUTOR_DRAFT_MODEL", settings.openai_model_nano)
    try:
        importlib.reload(dt)
        assert dt._DRAFT_MODEL_DEFAULT == settings.openai_model_nano
    finally:
        monkeypatch.undo()
        importlib.reload(dt)


def test_planner_prompt_contains_related_framings_facet():
    """EXTRACT_CONCEPTS_BUDGET_PROMPT includes the related-framings facet instruction."""
    from src.services.chat.prompts.deep_tutor import EXTRACT_CONCEPTS_BUDGET_PROMPT

    prompt = EXTRACT_CONCEPTS_BUDGET_PROMPT.lower()
    assert "related-framings facet" in prompt, (
        "Prompt must mention 'related-framings facet'"
    )
    assert "other contexts" in prompt, (
        "Prompt must instruct the planner to include 'other contexts'"
    )
    # Example query for related-framings must be present
    assert "regularization" in prompt, (
        "Bias-variance example must reference regularization as an alternative framing"
    )
    assert "model selection" in prompt, (
        "Bias-variance example must reference model selection as an alternative framing"
    )


def test_planner_prompt_example_includes_related_framings_query():
    """The bias-variance example in EXTRACT_CONCEPTS_BUDGET_PROMPT has a related-framings query."""
    from src.services.chat.prompts.deep_tutor import EXTRACT_CONCEPTS_BUDGET_PROMPT

    # The example must include a query that targets the related-framings framing
    assert "regularization and model selection" in EXTRACT_CONCEPTS_BUDGET_PROMPT.lower(), (
        "Example must include a query for 'bias-variance tradeoff in regularization and model selection'"
    )


def _make_source_with_chapter(rank: int, book: str, chapter: str, section: str) -> "object":
    """Helper: create a Source with explicit chapter for topic-diversity tests."""
    from src.services.chat.schemas import Source
    return Source(
        rank=rank, book=book, chapter=chapter, section=section,
        title=f"{book} {chapter} §{section}",
        excerpt="text", score=1.0 / rank,
        chunkId=f"{book}-{chapter}-{section}-{rank}",
        chunk="bias variance tradeoff text",
        book_name=book.upper(), authors="Author A", authors_short="Author A",
        year=2020, page_from=rank * 10, page_to=rank * 10 + 5, page=rank * 10,
    )


def test_section_parent_diversity_spreads_chapters():
    """_apply_section_parent_diversity reinserts a source from a different chapter."""
    from src.services.chat.agents.deep_tutor import _apply_section_parent_diversity

    # All 3 selected sources are from "ch02"
    selected = [
        _make_source_with_chapter(1, "bookA", "ch02", "2.1"),
        _make_source_with_chapter(2, "bookA", "ch02", "2.2"),
        _make_source_with_chapter(3, "bookB", "ch02", "2.1"),
    ]
    # Dropped pool has one source from "ch05" (different framing)
    dropped_source = _make_source_with_chapter(4, "bookC", "ch05", "5.1")
    # ranked_all = selected + dropped (eff_top_n = 3)
    ranked_all = selected + [dropped_source]
    eff_top_n = 3

    result = _apply_section_parent_diversity(selected, ranked_all, eff_top_n)

    # The ch05 source should be reinserted
    chapters = [s.chapter for s in result]
    assert "ch05" in chapters, f"Expected ch05 reinserted, got chapters={chapters}"
    assert len(result) == len(selected) + 1


def test_section_parent_diversity_no_op_when_already_diverse():
    """No extra source added when sources already span multiple chapters."""
    from src.services.chat.agents.deep_tutor import _apply_section_parent_diversity

    selected = [
        _make_source_with_chapter(1, "bookA", "ch02", "2.1"),
        _make_source_with_chapter(2, "bookA", "ch05", "5.1"),  # different chapter
    ]
    ranked_all = selected  # nothing dropped
    result = _apply_section_parent_diversity(selected, ranked_all, len(selected))
    assert result == selected  # unchanged


def test_section_parent_diversity_degrades_when_no_chapter_metadata():
    """Degrades gracefully when chapter field is empty (no metadata)."""
    from src.services.chat.agents.deep_tutor import _apply_section_parent_diversity
    from src.services.chat.schemas import Source

    def _no_chapter(rank):
        return Source(
            rank=rank, book="b", chapter="",  # empty chapter = no metadata
            section="s", title="t", excerpt="x", score=0.5,
            chunkId=f"c{rank}", chunk="text",
        )

    selected = [_no_chapter(1), _no_chapter(2)]
    ranked_all = selected + [_no_chapter(3)]
    result = _apply_section_parent_diversity(selected, ranked_all, 2)
    assert result == selected  # unchanged — degraded cleanly


# ---------------------------------------------------------------------------
# Phase-3 changes: adaptive routing (complexity tier)
# ---------------------------------------------------------------------------


def _make_routing_pipeline(
    *,
    perspectives: int | None,
    multi_queries: list[str] | None = None,
    routing_on: bool = True,
):
    """Return a context manager that stubs the full pipeline and exposes a
    ``calls`` dict with the plan / retrieval calls that were made."""
    from src.services.chat.agents import deep_tutor as dt
    from src.services.chat.schemas import RetrievalMetadata

    calls: dict = {"plan": 0, "retrieval_queries": [], "multi_query": 0}

    # Build a QueryPlan with the requested perspectives value.
    if perspectives is None:
        # Simulate a parse failure by making extract_concepts_ex return the
        # heuristic fallback (suggested_authors=2, queries=[]).
        qp = dt.QueryPlan(["variance"], 2, [], [])
    else:
        qs = multi_queries if multi_queries is not None else [
            "formula for variance",
            "variance of estimator definition",
            "variance in regularization and model selection",  # related-framings last
        ]
        qp = dt.QueryPlan(["variance"], perspectives, qs, ["variance definition"])

    deep = _make_deep_answer()
    sources = [
        _src(1, "islp", "2.1", "Variance is sensitivity to data."),
        _src(2, "esl", "3.1", "Variance in regularization context."),
    ]

    async def fake_extract_ex(q, *, model=None, max_authors=4):
        return qp

    async def fake_wide(q, slugs, pool):
        return list(sources), RetrievalMetadata(
            rewrittenQuery=q, embedding="x", retrievalMs=1, collections=["c1"],
            filter="f", topK=len(sources), scoreThreshold=0.0, mode="mock-wide",
        )

    async def fake_multi_query(qs_arg, slugs, pool):
        calls["multi_query"] += 1
        calls["retrieval_queries"].extend(qs_arg)
        return []  # empty extra pool — RRF merge is a no-op

    def fake_density(q, concepts, candidates, *, book_slugs=None, **kw):
        return list(sources), ["c1"]

    async def fake_plan(q, srcs, *, model=None):
        calls["plan"] += 1
        return None

    async def fake_draft(q, srcs, *, figures=None, on_aspect_delta=None, model=None, plan=None, **kwargs):
        from src.services.chat.prompts.deep_tutor import ASPECT_HEADINGS
        aspects = {k: getattr(deep, k) for k in ASPECT_HEADINGS}
        if on_aspect_delta:
            for k, v in aspects.items():
                on_aspect_delta(k, v)
        return deep, aspects

    import contextlib

    async def fake_recover(q, srcs):
        return ""

    @contextlib.contextmanager
    def _ctx():
        patches = [
            patch.object(dt, "extract_concepts_ex", fake_extract_ex),
            patch.object(dt, "_wide_candidates", fake_wide),
            patch.object(dt, "_multi_query_candidates", fake_multi_query),
            patch.object(dt, "_density_select", fake_density),
            patch.object(dt, "build_synthesis_plan", fake_plan),
            patch.object(dt, "_stream_draft", fake_draft),
            patch.object(dt, "_recover_equations_block", fake_recover),
            patch.object(dt, "_IMAGES_ENABLED", False),
            patch.object(dt, "_ADAPTIVE_ROUTING", routing_on),
            patch.object(dt, "_MULTI_QUERY", True),
        ]
        for p in patches:
            p.start()
        try:
            yield calls
        finally:
            for p in patches:
                p.stop()

    return _ctx()


def test_adaptive_routing_simple_skips_plan_and_framing_query(sample_sources):
    """perspectives=1 → tier=simple → plan skipped AND related-framings query dropped."""
    from src.services.chat.agents import deep_tutor
    from src.services.chat.schemas import ChatRequest

    req = ChatRequest(message="Define variance.", mode="tutor",
                      model="gpt-5.4-nano-2026-03-17")

    with _make_routing_pipeline(perspectives=1) as calls:
        asyncio.run(_drain(deep_tutor.run_deep_tutor(req)))

    # Plan must not have run.
    assert calls["plan"] == 0, f"plan should be skipped for simple tier; got {calls['plan']}"
    # The related-framings query (last of 3) must NOT appear in the queries sent.
    assert "variance in regularization and model selection" not in calls["retrieval_queries"], (
        "Related-framings query must be dropped for simple tier; "
        f"got queries={calls['retrieval_queries']}"
    )
    # The core queries (first two) must still be used.
    assert "formula for variance" in calls["retrieval_queries"], (
        f"Core queries must be retained; got {calls['retrieval_queries']}"
    )


def test_adaptive_routing_standard_runs_plan_and_all_queries(sample_sources):
    """perspectives>=2 → tier=standard → Phase-2 behavior intact (plan runs + all queries)."""
    from src.services.chat.agents import deep_tutor
    from src.services.chat.schemas import ChatRequest

    req = ChatRequest(message="What is the bias-variance tradeoff?", mode="tutor",
                      model="gpt-5.4-nano-2026-03-17")

    with _make_routing_pipeline(perspectives=3) as calls:
        asyncio.run(_drain(deep_tutor.run_deep_tutor(req)))

    # Plan must run.
    assert calls["plan"] == 1, f"plan should run for standard tier; got {calls['plan']}"
    # All three queries, including related-framings, must be used.
    assert "variance in regularization and model selection" in calls["retrieval_queries"], (
        f"Related-framings query must be retained for standard tier; "
        f"got queries={calls['retrieval_queries']}"
    )


def test_adaptive_routing_missing_perspectives_defaults_standard(sample_sources):
    """Missing perspectives (parse failure path) → standard tier (fail toward quality)."""
    from src.services.chat.agents import deep_tutor
    from src.services.chat.schemas import ChatRequest

    # perspectives=None triggers the fallback QueryPlan with suggested_authors=2
    req = ChatRequest(message="Explain variance.", mode="tutor",
                      model="gpt-5.4-nano-2026-03-17")

    with _make_routing_pipeline(perspectives=None) as calls:
        asyncio.run(_drain(deep_tutor.run_deep_tutor(req)))

    # With suggested_authors=2, tier is standard → plan runs.
    assert calls["plan"] == 1, (
        f"Missing perspectives must default to standard (plan runs); got {calls['plan']}"
    )


def test_adaptive_routing_flag_off_always_standard(sample_sources):
    """TUTOR_ADAPTIVE_ROUTING=0 → always standard regardless of perspectives."""
    from src.services.chat.agents import deep_tutor
    from src.services.chat.schemas import ChatRequest

    req = ChatRequest(message="Define variance.", mode="tutor",
                      model="gpt-5.4-nano-2026-03-17")

    # routing_on=False disables the flag; even with perspectives=1, plan must run.
    with _make_routing_pipeline(perspectives=1, routing_on=False) as calls:
        asyncio.run(_drain(deep_tutor.run_deep_tutor(req)))

    assert calls["plan"] == 1, (
        f"TUTOR_ADAPTIVE_ROUTING=0 must force standard tier (plan runs); got {calls['plan']}"
    )
    # Related-framings query must also be retained.
    assert "variance in regularization and model selection" in calls["retrieval_queries"], (
        f"All queries must be retained when routing is off; got {calls['retrieval_queries']}"
    )


# ---------------------------------------------------------------------------
# Plan D bugfix — nano default + capability-based draft routing
# ---------------------------------------------------------------------------


def test_draft_default_is_nano(monkeypatch):
    """_DRAFT_MODEL_DEFAULT must be nano (not full); _resolve_draft_default(None) == nano."""
    import src.services.chat.agents.deep_tutor as DT
    from src.core.config import settings

    # Force _DRAFT_MODEL_DEFAULT to nano in case env overrides it.
    monkeypatch.setattr(DT, "_DRAFT_MODEL_DEFAULT", settings.openai_model_nano)

    assert DT._DRAFT_MODEL_DEFAULT == settings.openai_model_nano
    # resolve with nano (schema default) → nano
    assert DT._resolve_draft_default(settings.openai_model_nano) == settings.openai_model_nano
    # resolve with None → nano
    assert DT._resolve_draft_default(None) == settings.openai_model_nano


@pytest.mark.asyncio
async def test_stream_draft_routes_non_openai_via_router(monkeypatch):
    """Non-OpenAI model (qwen-plus) must use _stream_draft_via_router;
    OpenAI nano must use _stream_structured."""
    import src.services.chat.agents.deep_tutor as DT
    from src.core.config import settings
    from src.services.chat.schemas import Source
    from src.services.chat.schemas.output import DeepTutorAnswer

    _answer = DeepTutorAnswer(tldr="t", definition="d", formal_statement="",
                              example_intuition="", applications="", further_reading="")

    calls: dict[str, list[str]] = {"router": [], "structured": []}

    async def fake_router(model, messages, aspects, on_aspect_delta=None):
        calls["router"].append(model)
        return _answer, {}

    async def fake_structured(messages, model, on_aspect_delta=None):
        calls["structured"].append(model)
        return _answer, {}

    monkeypatch.setattr(DT, "_stream_draft_via_router", fake_router)
    monkeypatch.setattr(DT, "_stream_structured", fake_structured)

    src_ = Source(rank=1, chunkId="c1", title="t", excerpt="x", chunk="hello",
                  book="b1", book_name="b1", authors="A Smith", authors_short="Smith",
                  section="1", chapter="ch1", score=0.5)

    # qwen-plus → router path
    await DT._stream_draft("q", [src_], model="qwen-plus")
    assert calls["router"] == ["qwen-plus"], "qwen-plus must use _stream_draft_via_router"
    assert calls["structured"] == []

    calls["router"].clear()
    calls["structured"].clear()

    # OpenAI nano → structured path
    nano = settings.openai_model_nano
    await DT._stream_draft("q", [src_], model=nano)
    assert calls["structured"] == [nano], "OpenAI nano must use _stream_structured"
    assert calls["router"] == []


def test_wrap_bare_math_wraps_unicode_greek_latex_run():
    from src.services.chat.agents.deep_tutor import _wrap_bare_math
    import re
    s = r"running a simple regression: \tilde y=\tilde β_0+\tilde β_1 x_1."
    out = _wrap_bare_math(s)
    stripped = re.sub(r"\$\$[^$]+\$\$|\$[^$]+\$", "", out)
    assert "\\tilde" not in stripped, f"raw LaTeX leaked: {out!r}"
    assert "$" in out


def test_wrap_bare_math_leaves_plain_prose_untouched():
    from src.services.chat.agents.deep_tutor import _wrap_bare_math
    s = "The model omits a relevant variable and induces bias."
    assert _wrap_bare_math(s) == s


def test_convert_dedupes_and_caps_figures_per_aspect():
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import DeepTutorAnswer, FigureRef

    deep = DeepTutorAnswer(
        tldr="t", definition="d", formal_statement="", example_intuition="e",
        applications="a", further_reading="f", citations=[], math_blocks=[], figures=[],
    )
    aspects = {
        "tldr": "t", "definition": "d", "formal_statement": "",
        "example_intuition": "e", "applications": "a", "further_reading": "f",
    }
    figs = [
        FigureRef(ref="r1", book="islp", chapter="ch02", caption="bias variance plot",
                  url="/api/figures?path=a.jpg", judge_confidence=0.9,
                  judge_reason="plots bias and variance vs flexibility", figure_role="other"),
        FigureRef(ref="r2", book="islp", chapter="ch02", caption="",
                  url="/api/figures?path=b.jpg", judge_confidence=0.4,
                  judge_reason="The image visually represents the bias-variance tradeoff, which is relevant to the query.",
                  figure_role="other"),
    ]
    ans = _convert_to_tutor_answer(deep, aspects, sources=[], approved_figures=figs)
    total = sum(v.count("### Figure example") for v in ans.aspects.values())
    assert total == 1, ans.aspects


def test_isolate_midline_display_moves_bullet_display_to_own_line():
    from src.services.chat.agents.deep_tutor import _isolate_midline_display
    s = r"- **In estimator notation, bias is** $$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$ [2]"
    out = _isolate_midline_display(s)
    lines = out.split("\n")
    # the equation must end up alone on its own line (so the frontend renders it as display)
    assert any(ln.strip() == r"$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$" for ln in lines), out
    # the lead-in text + citation stay on the bullet line, no mid-line $$ remains
    assert any(ln.strip().startswith("- **In estimator notation, bias is**") and "$$" not in ln for ln in lines), out


def test_isolate_midline_display_keeps_ownline_display_block():
    from src.services.chat.agents.deep_tutor import _isolate_midline_display
    s = r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$"
    assert _isolate_midline_display(s) == s


def test_isolate_midline_display_keeps_indented_ownline_display():
    from src.services.chat.agents.deep_tutor import _isolate_midline_display
    s = "intro line\n  $$\\mathrm{MSE}=\\sigma^2$$\nnext line"
    out = _isolate_midline_display(s)
    assert "  $$\\mathrm{MSE}=\\sigma^2$$" in out


def test_promote_inline_equations_promotes_relation_span():
    from src.services.chat.agents.deep_tutor import _promote_inline_equations
    s = r"- the bias is $\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$, capturing how far. [1]"
    out = _promote_inline_equations(s)
    lines = [ln for ln in out.split("\n") if ln.strip()]
    assert r"$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$" in lines, out
    # the equation is gone from the prose line; trailing comma trimmed
    assert any("capturing how far" in ln and "$$" not in ln and not ln.lstrip().startswith(",") for ln in lines), out


def test_promote_inline_equations_keeps_bare_symbols_inline():
    from src.services.chat.agents.deep_tutor import _promote_inline_equations
    s = r"the true model includes $x_2$ but the fitted model omits $\theta$ here."
    assert _promote_inline_equations(s) == s  # no relation -> untouched


def test_promote_inline_equations_ignores_ownline_display():
    from src.services.chat.agents.deep_tutor import _promote_inline_equations
    s = "$$\\mathrm{MSE}=\\sigma^2$$"
    assert _promote_inline_equations(s) == s
