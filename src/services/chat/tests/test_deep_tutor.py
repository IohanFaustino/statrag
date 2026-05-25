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

    async def fake_draft(q, srcs, *, figures=None, on_aspect_delta=None, model=None, plan=None):
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

    patches = [
        patch.object(dt, "extract_concepts", fake_extract),
        patch.object(dt, "extract_concepts_ex", fake_extract_ex),
        patch.object(dt, "build_synthesis_plan", fake_plan),
        patch.object(dt, "_wide_candidates", fake_wide),
        patch.object(dt, "_density_select", fake_density),
        patch.object(dt, "_stream_draft", fake_draft),
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
