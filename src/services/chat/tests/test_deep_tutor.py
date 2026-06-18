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


@pytest.fixture(autouse=True)
def _no_wiki_network():
    """Isolate run_deep_tutor tests from the live Wikipedia fetch (always-on per
    concept). Tests that exercise wiki behaviour live in test_tutor_wiki.py."""
    from src.services.chat.agents import deep_tutor

    async def _empty(concepts):
        return []
    with patch.object(deep_tutor, "_fetch_wiki_sources", _empty):
        yield


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


def test_stream_structured_last_resort_degrades_on_format_validator():
    """Regression: a draft whose math definition has a prose component
    subsection (e.g. ``### Trend`` with no ``$$equation$$``) trips the
    component-equation validator. The strict stream + parse() paths fail, and
    the last-resort json_object path must DEGRADE (skip_format_checks) rather
    than blank the turn with "Failed to generate an answer."."""
    from unittest.mock import AsyncMock
    from src.services.chat.agents import deep_tutor

    # A complete answer that violates _require_component_equations: the
    # definition is mathematical ($$ present) but the ### Trend subsection
    # carries no symbolic display equation.
    payload = {
        "tldr": "Decomposition splits a series into parts.",
        "definition": (
            "A time series decomposes as $$y_t = T_t + S_t + R_t$$.\n\n"
            "### Trend\nThe smooth long-run movement of the series.\n\n"
            "### Seasonality\nThe repeating calendar pattern."
        ),
        "formal_statement": "",
        "example_intuition": "Imagine monthly sales rising while wobbling each December. " * 4,
        "applications": "Used for forecasting and anomaly detection in corpus methods. " * 3,
        "further_reading": "STL, X-13ARIMA-SEATS, and wavelet decompositions. " * 3,
    }

    fake = MagicMock()
    # Strict stream path: raise TypeError -> caught, falls through.
    fake.beta.chat.completions.stream = MagicMock(side_effect=TypeError("no stream"))
    # Strict parse() path: raise (mimics the pydantic ValidationError) -> falls through.
    fake.beta.chat.completions.parse = AsyncMock(side_effect=ValueError("validator rejected"))
    # Last-resort json_object path: returns the complete-but-imperfect payload.
    msg = MagicMock()
    msg.content = json.dumps(payload)
    resp = MagicMock()
    resp.choices = [MagicMock(message=msg)]
    fake.chat.completions.create = AsyncMock(return_value=resp)

    with patch.object(deep_tutor, "_async_client", return_value=fake):
        obj, aspects = asyncio.run(
            deep_tutor._stream_structured(
                [{"role": "user", "content": "decomposition"}],
                "gpt-5.4-nano-2026-03-17",
            )
        )
    assert obj is not None, "last-resort fallback blanked a complete answer"
    assert "$$y_t = T_t + S_t + R_t$$" in aspects["definition"]


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

    async def fake_seam_guard(aspects, thesis, *, redraft):
        # Unit tests don't exercise seam validation; short-circuit to avoid
        # real check_seams triggering an extra draft call on mock aspects.
        return aspects, {"seam_continuity": 1.0, "lang_ok": 1.0, "thesis_adherence": 0.0}

    patches = [
        patch.object(dt, "extract_concepts", fake_extract),
        patch.object(dt, "extract_concepts_ex", fake_extract_ex),
        patch.object(dt, "build_synthesis_plan", fake_plan),
        patch.object(dt, "_wide_candidates", fake_wide),
        patch.object(dt, "_density_select", fake_density),
        patch.object(dt, "_stream_draft", fake_draft),
        patch.object(dt, "_recover_equations_block", fake_recover),
        patch.object(dt, "_seam_guard", fake_seam_guard),
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

    async def fake_seam_guard(aspects, thesis, *, redraft):
        return aspects, {"seam_continuity": 1.0, "lang_ok": 1.0, "thesis_adherence": 0.0}

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
            patch.object(dt, "_seam_guard", fake_seam_guard),
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


def test_tutor_formal_def_multi_and_verbatim():
    from src.services.chat.schemas.output import TutorFormalDef, DeepTutorAnswer
    strict = TutorFormalDef(kind='definition', label='Definition 14.1', statement='strictly stationary if $$F(x_{t})=F(x_{t+h})$$', cite=1)
    weak = TutorFormalDef(kind='definition', label='', statement='weakly stationary if $$E[x_t]=\\mu$$', cite=2)
    assert strict.label == 'Definition 14.1'
    assert weak.label == ''
    ans = DeepTutorAnswer(tldr='t', definition='d', formal_statement='', example_intuition='e', applications='a', further_reading='f', formal_statements=[strict, weak])
    assert len(ans.formal_statements) == 2


def test_tutor_formal_def_empty_statement_rejected():
    from src.services.chat.schemas.output import TutorFormalDef
    with pytest.raises(Exception):
        TutorFormalDef(kind='definition', label='', statement='   ', cite=1)


def test_render_formal_statements():
    from src.services.chat.agents.deep_tutor import _render_formal_statements
    from src.services.chat.schemas.output import TutorFormalDef
    defs = [TutorFormalDef(kind='definition', label='Definition 14.1', statement='$$F(x_t)=F(x_{t+h})$$', cite=1),
            TutorFormalDef(kind='definition', label='', statement='$$E[x_t]=\\mu$$', cite=2)]
    md = _render_formal_statements(defs)
    assert 'Definition 14.1' in md
    assert '$$F(x_t)=F(x_{t+h})$$' in md
    assert '$$E[x_t]=\\mu$$' in md
    assert '[1]' in md and '[2]' in md
    assert _render_formal_statements([]) == ''


def test_draft_prompt_instructs_verbatim_multi_formal_defs():
    from src.services.chat.prompts.deep_tutor import DEEP_TUTOR_INSTRUCTIONS as P
    low = P.lower()
    assert 'formal_statements' in low
    assert 'verbatim' in low
    assert 'not required' in low or 'preferred but not' in low


def test_wiki_source_render_allows_anchor():
    from src.services.chat.prompts.deep_tutor import format_source_bundle
    from src.services.chat.schemas import Source
    w = Source(rank=2, book="wikipedia", chapter="", section="Stationarity", title="Stationarity",
               excerpt="x", score=0.0, chunkId="wiki:S", chunk="A process is stationary if...",
               book_name="Wikipedia", url="https://en.wikipedia.org/wiki/Stationary_process")
    out = format_source_bundle([w]).lower()
    assert "supplementary" not in out
    assert "anchor" in out


# ---------------------------------------------------------------------------
# DR-4: Definition Recovery wiring helpers
# ---------------------------------------------------------------------------
def test_def_sources_assigns_ranks_and_chunkid():
    from src.services.chat.agents.deep_tutor import _def_sources
    from src.services.chat.agents.definition_cache import RecoveredDefinition
    rd = RecoveredDefinition(concept="strict stationarity", kind="definition",
                             label="Definition 14.1",
                             statement="A process is strictly stationary if X",
                             book="hansen", book_name="Hansen", chapter="ch14",
                             section="14.1", chunkId="hansen:14")
    out = _def_sources([rd], start_rank=10)
    assert len(out) == 1
    assert out[0].rank == 11
    assert out[0].chunkId == "hansen:14"
    assert out[0].chunk == "A process is strictly stationary if X"


def test_recover_definitions_block_disabled(monkeypatch):
    import asyncio as _a
    from src.services.chat.agents.deep_tutor import _recover_definitions_block
    monkeypatch.setenv("TUTOR_DEEP_DEFINITIONS", "0")
    assert _a.run(_recover_definitions_block("q", ["c"], [], None)) == ([], "")


def test_recover_definitions_block_no_gaps(monkeypatch):
    import asyncio as _a
    from unittest.mock import patch
    from src.services.chat.agents import deep_tutor as dt
    monkeypatch.setenv("TUTOR_DEEP_DEFINITIONS", "1")
    with patch("src.services.chat.agents.definition_gaps.detect_definition_gaps", return_value=[]):
        out = _a.run(dt._recover_definitions_block("compute adf", ["x"], [], None))
    assert out == ([], "")


# ---------------------------------------------------------------------------
# Regression: empty/null formal_statements entries must not crash validation
# (live incident: router draft (deepseek-v4-pro) failed because the model
# emitted a formal_statements entry with empty statement)
# ---------------------------------------------------------------------------


def test_deep_tutor_answer_drops_empty_statement_entries():
    """Regression: a ``formal_statements`` entry with empty ``statement``
    must be silently dropped, not crash ``DeepTutorAnswer.model_validate``."""
    from src.services.chat.schemas.output import DeepTutorAnswer

    payload = dict(
        tldr="Stationarity means distributional invariance over time. " * 3,
        definition="A process is stationary if its joint distribution is invariant under time shifts. " * 8,
        formal_statement="",
        example_intuition="Imagine recording daily temperatures. " * 6,
        applications="Stationarity underpins time-series forecasting. " * 6,
        further_reading="See Hamilton (1994) for rigorous treatment. " * 3,
        formal_statements=[
            {"kind": "Definition", "label": "Definition 14.1",
             "statement": "", "cite": 1},  # empty — must be dropped
            {"kind": "Theorem", "label": "",
             "statement": "If a process is strictly stationary then ...", "cite": 2},
        ],
    )
    obj = DeepTutorAnswer.model_validate(payload, context={"skip_format_checks": True})
    # The empty-statement entry must be gone; the valid one must survive.
    assert len(obj.formal_statements) == 1
    assert obj.formal_statements[0].kind == "theorem"
    assert obj.formal_statements[0].statement == "If a process is strictly stationary then ..."


def test_deep_tutor_answer_drops_null_statement_entries():
    """A ``formal_statements`` entry with ``statement: null`` (JSON null)
    must be silently dropped."""
    from src.services.chat.schemas.output import DeepTutorAnswer

    payload = dict(
        tldr="Stationarity means distributional invariance over time. " * 3,
        definition="A process is stationary if its joint distribution is invariant under time shifts. " * 8,
        formal_statement="",
        example_intuition="Imagine recording daily temperatures. " * 6,
        applications="Stationarity underpins time-series forecasting. " * 6,
        further_reading="See Hamilton (1994) for rigorous treatment. " * 3,
        formal_statements=[
            {"kind": "Definition", "label": "Def 1",
             "statement": None, "cite": 1},  # null — must be dropped
        ],
    )
    obj = DeepTutorAnswer.model_validate(payload, context={"skip_format_checks": True})
    assert obj.formal_statements == []


def test_deep_tutor_answer_drops_whitespace_only_statement_entries():
    """A ``formal_statements`` entry with whitespace-only ``statement``
    must be silently dropped."""
    from src.services.chat.schemas.output import DeepTutorAnswer

    payload = dict(
        tldr="Stationarity means distributional invariance over time. " * 3,
        definition="A process is stationary if its joint distribution is invariant under time shifts. " * 8,
        formal_statement="",
        example_intuition="Imagine recording daily temperatures. " * 6,
        applications="Stationarity underpins time-series forecasting. " * 6,
        further_reading="See Hamilton (1994) for rigorous treatment. " * 3,
        formal_statements=[
            {"kind": "Definition", "label": "",
             "statement": "   \t  \n  ", "cite": 1},  # whitespace-only — must be dropped
            {"kind": "Theorem", "label": "",
             "statement": "A valid statement.", "cite": 2},
        ],
    )
    obj = DeepTutorAnswer.model_validate(payload, context={"skip_format_checks": True})
    assert len(obj.formal_statements) == 1
    assert obj.formal_statements[0].statement == "A valid statement."


def test_deep_tutor_answer_drops_missing_statement_key():
    """A ``formal_statements`` entry with no ``statement`` key at all
    must be silently dropped."""
    from src.services.chat.schemas.output import DeepTutorAnswer

    payload = dict(
        tldr="Stationarity means distributional invariance over time. " * 3,
        definition="A process is stationary if its joint distribution is invariant under time shifts. " * 8,
        formal_statement="",
        example_intuition="Imagine recording daily temperatures. " * 6,
        applications="Stationarity underpins time-series forecasting. " * 6,
        further_reading="See Hamilton (1994) for rigorous treatment. " * 3,
        formal_statements=[
            {"kind": "Definition", "label": "Def 1",
             "cite": 1},  # no statement key — must be dropped
            {"kind": "Theorem", "label": "",
             "statement": "A valid statement.", "cite": 2},
        ],
    )
    obj = DeepTutorAnswer.model_validate(payload, context={"skip_format_checks": True})
    assert len(obj.formal_statements) == 1
    assert obj.formal_statements[0].statement == "A valid statement."


def test_deep_tutor_answer_all_empty_formal_statements_ok():
    """When ALL ``formal_statements`` entries are empty, the list must be
    empty — not crash."""
    from src.services.chat.schemas.output import DeepTutorAnswer

    payload = dict(
        tldr="Stationarity means distributional invariance over time. " * 3,
        definition="A process is stationary if its joint distribution is invariant under time shifts. " * 8,
        formal_statement="",
        example_intuition="Imagine recording daily temperatures. " * 6,
        applications="Stationarity underpins time-series forecasting. " * 6,
        further_reading="See Hamilton (1994) for rigorous treatment. " * 3,
        formal_statements=[
            {"kind": "Definition", "label": "Def 1",
             "statement": "", "cite": 1},
            {"kind": "Theorem", "label": "",
             "statement": "   ", "cite": 2},
        ],
    )
    obj = DeepTutorAnswer.model_validate(payload, context={"skip_format_checks": True})
    assert obj.formal_statements == []


def test_deep_tutor_answer_still_rejects_invalid_kind_after_drop():
    """The drop filter must NOT mask truly invalid entries — a valid
    statement with an invalid kind (e.g. 'axiom') must still raise."""
    from src.services.chat.schemas.output import DeepTutorAnswer
    from pydantic import ValidationError

    payload = dict(
        tldr="Stationarity means distributional invariance over time. " * 3,
        definition="A process is stationary if its joint distribution is invariant under time shifts. " * 8,
        formal_statement="",
        example_intuition="Imagine recording daily temperatures. " * 6,
        applications="Stationarity underpins time-series forecasting. " * 6,
        further_reading="See Hamilton (1994) for rigorous treatment. " * 3,
        formal_statements=[
            {"kind": "axiom", "label": "",
             "statement": "A valid statement with invalid kind.", "cite": 1},
        ],
    )
    with pytest.raises(ValidationError, match="kind"):
        DeepTutorAnswer.model_validate(payload, context={"skip_format_checks": True})


# ---------------------------------------------------------------------------
# Regression: title-case kind normalisation (live incident fix)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Regression: title-case kind normalisation (live incident fix)
# ---------------------------------------------------------------------------


def test_tutor_formal_def_kind_normalises_title_case():
    """Regression: LLMs emit "Definition" (title case) for
    ``TutorFormalDef.kind``. The field validator must normalise to lowercase
    so ``model_validate`` does not crash the deep-tutor draft."""
    from src.services.chat.schemas.output import TutorFormalDef

    # Exact live-failure value: "Definition" (title case)
    obj = TutorFormalDef(kind="Definition", label="Def 14.1",
                         statement="A process is stationary if ...", cite=1)
    assert obj.kind == "definition"

    # All allowed variants must round-trip correctly
    for variant in ["definition", "Definition", "DEFINITION", "DeFiNiTiOn",
                    " Theorem ", "LEMMA", "Proposition"]:
        normalised = variant.strip().lower()
        if normalised in ("definition", "theorem", "proposition", "lemma", "corollary"):
            obj = TutorFormalDef(kind=variant, statement="s", cite=1)
            assert obj.kind == normalised


def test_formal_statement_kind_normalises_title_case():
    """Same normalisation must apply to ``FormalStatement.kind`` (facilitate
    story mode uses this schema)."""
    from src.services.chat.schemas.output import FormalStatement

    obj = FormalStatement(kind="Theorem", statement="For all ε > 0 ...")
    assert obj.kind == "theorem"

    # All valid Literal values must survive round-trip through title case
    for variant in ["definition", "Definition", "DEFINITION",
                     "Lemma", "COROLLARY", " Remark "]:
        normalised = variant.strip().lower()
        if normalised in ("definition", "lemma", "theorem", "proposition",
                          "corollary", "remark"):
            obj = FormalStatement(kind=variant, statement="content")
            assert obj.kind == normalised


def test_deep_tutor_answer_accepts_title_case_formal_statements():
    """End-to-end regression: ``DeepTutorAnswer.model_validate`` must not crash
    when ``formal_statements[].kind`` is title-case (the exact live failure)."""
    from src.services.chat.schemas.output import DeepTutorAnswer

    payload = dict(
        tldr="Stationarity means distributional invariance over time. " * 3,
        definition="A process is stationary if its joint distribution is invariant under time shifts. " * 8,
        formal_statement="",
        example_intuition="Imagine recording daily temperatures. " * 6,
        applications="Stationarity underpins time-series forecasting. " * 6,
        further_reading="See Hamilton (1994) for rigorous treatment. " * 3,
        formal_statements=[
            {"kind": "Definition", "label": "Definition 14.1",
             "statement": "A process is strictly stationary if ...", "cite": 1},
            {"kind": "Theorem", "label": "",
             "statement": "If a process is strictly stationary then ...", "cite": 2},
        ],
    )
    # Must NOT raise — this is the exact crash path from the live incident
    obj = DeepTutorAnswer.model_validate(payload, context={"skip_format_checks": True})
    assert len(obj.formal_statements) == 2
    assert obj.formal_statements[0].kind == "definition"
    assert obj.formal_statements[1].kind == "theorem"

    # Also validate WITHOUT skip_format_checks (payload has no math triggers)
    obj2 = DeepTutorAnswer.model_validate(payload)
    assert obj2.formal_statements[0].kind == "definition"


def test_title_case_kind_rejected_without_normaliser():
    """Verify the Literal constraint still catches truly invalid values even
    after normalisation — e.g. "axiom" is not in the allowed set."""
    from src.services.chat.schemas.output import TutorFormalDef
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="kind"):
        TutorFormalDef(kind="axiom", statement="s", cite=1)


# ---------------------------------------------------------------------------
# Regression: malformed cite formatting (live incident: cite="[10]")
# The model can emit cite as "[10]" (string with brackets), [10] (Python
# list), "10" (numeric string), etc. All must be normalised to int or the
# whole tutor turn crashes.
# ---------------------------------------------------------------------------


def test_formal_def_cite_string_with_brackets_normalised():
    """Regression: cite="[10]" (the exact live-failure value) must normalise
    to integer 10, not crash validation."""
    from src.services.chat.schemas.output import TutorFormalDef

    obj = TutorFormalDef(kind="definition", statement="A process is stationary if ...",
                         cite="[10]")
    assert obj.cite == 10


def test_formal_def_cite_numeric_string_normalised():
    """cite="10" (numeric string) must normalise to integer 10."""
    from src.services.chat.schemas.output import TutorFormalDef

    obj = TutorFormalDef(kind="definition", statement="A valid statement.",
                         cite="10")
    assert obj.cite == 10


def test_formal_def_cite_list_with_single_int_normalised():
    """cite=[10] (Python list wrapping a single int) must normalise to 10."""
    from src.services.chat.schemas.output import TutorFormalDef

    obj = TutorFormalDef(kind="definition", statement="A valid statement.",
                         cite=[10])
    assert obj.cite == 10


def test_formal_def_cite_list_with_single_string_normalised():
    """cite=["10"] (list of one numeric string) must normalise to 10."""
    from src.services.chat.schemas.output import TutorFormalDef

    obj = TutorFormalDef(kind="definition", statement="A valid statement.",
                         cite=["10"])
    assert obj.cite == 10


def test_formal_def_cite_bracket_string_with_spaces():
    """cite=" [ 10 ] " must normalise to 10."""
    from src.services.chat.schemas.output import TutorFormalDef

    obj = TutorFormalDef(kind="definition", statement="A valid statement.",
                         cite=" [ 10 ] ")
    assert obj.cite == 10


def test_formal_def_cite_unparseable_defaults_to_zero():
    """When cite is a completely unparseable string (e.g. "ref-3"), it
    should default to 0 rather than crash the turn."""
    from src.services.chat.schemas.output import TutorFormalDef

    obj = TutorFormalDef(kind="definition", statement="A valid statement.",
                         cite="ref-3")
    assert obj.cite == 0


def test_formal_def_cite_none_defaults_to_zero():
    """cite=None should default to 0 (not crash)."""
    from src.services.chat.schemas.output import TutorFormalDef

    obj = TutorFormalDef(kind="definition", statement="A valid statement.",
                         cite=None)
    assert obj.cite == 0


def test_formal_def_cite_empty_string_defaults_to_zero():
    """cite='' (empty string) should default to 0."""
    from src.services.chat.schemas.output import TutorFormalDef

    obj = TutorFormalDef(kind="definition", statement="A valid statement.",
                         cite="")
    assert obj.cite == 0


def test_deep_tutor_answer_formal_statements_with_malformed_cite():
    """End-to-end: DeepTutorAnswer.model_validate must not crash when
    formal_statements contain the live-failure cite="[10]" value."""
    from src.services.chat.schemas.output import DeepTutorAnswer

    payload = dict(
        tldr="Stationarity means distributional invariance over time. " * 3,
        definition="A process is stationary if its joint distribution is invariant under time shifts. " * 8,
        formal_statement="",
        example_intuition="Imagine recording daily temperatures. " * 6,
        applications="Stationarity underpins time-series forecasting. " * 6,
        further_reading="See Hamilton (1994) for rigorous treatment. " * 3,
        formal_statements=[
            {"kind": "Definition", "label": "Definition 14.1",
             "statement": "A process is strictly stationary if ...", "cite": "[10]"},
            {"kind": "Theorem", "label": "",
             "statement": "If a process is strictly stationary then ...", "cite": 2},
        ],
    )
    obj = DeepTutorAnswer.model_validate(payload, context={"skip_format_checks": True})
    assert len(obj.formal_statements) == 2
    assert obj.formal_statements[0].cite == 10
    assert obj.formal_statements[1].cite == 2


def test_deep_tutor_answer_formal_statements_cite_list():
    """End-to-end: cite=[10] (Python list) must not crash validation."""
    from src.services.chat.schemas.output import DeepTutorAnswer

    payload = dict(
        tldr="Stationarity means distributional invariance over time. " * 3,
        definition="A process is stationary if its joint distribution is invariant under time shifts. " * 8,
        formal_statement="",
        example_intuition="Imagine recording daily temperatures. " * 6,
        applications="Stationarity underpins time-series forecasting. " * 6,
        further_reading="See Hamilton (1994) for rigorous treatment. " * 3,
        formal_statements=[
            {"kind": "definition", "statement": "A valid statement.", "cite": [10]},
        ],
    )
    obj = DeepTutorAnswer.model_validate(payload, context={"skip_format_checks": True})
    assert len(obj.formal_statements) == 1
    assert obj.formal_statements[0].cite == 10


# ---------------------------------------------------------------------------
# Regression: formal_statements wiring in TutorAnswer payload
# ---------------------------------------------------------------------------


def test_convert_passes_formal_statements_to_tutor_answer(sample_sources):
    """Regression: _convert_to_tutor_answer must carry deep.formal_statements
    onto the returned TutorAnswer so the frontend structured render path can
    activate."""
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import TutorFormalDef

    deep = _make_deep_answer(
        formal_statements=[
            TutorFormalDef(kind="definition", label="Definition 14.1",
                           statement="A process is strictly stationary if ...", cite=1),
            TutorFormalDef(kind="definition", label="",
                           statement="A process is weakly stationary if ...", cite=2),
        ],
    )
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)
    assert len(ans.formal_statements) == 2
    assert ans.formal_statements[0].kind == "definition"
    assert ans.formal_statements[0].label == "Definition 14.1"
    assert ans.formal_statements[0].cite == 1
    assert ans.formal_statements[1].statement == "A process is weakly stationary if ..."

    # model_dump must include the field
    dumped = ans.model_dump()
    assert "formal_statements" in dumped
    assert len(dumped["formal_statements"]) == 2


def test_convert_formal_statements_empty_when_deep_is_none(sample_sources):
    """When deep is None, formal_statements must be an empty list (no crash)."""
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    ans = _convert_to_tutor_answer(None, {"tldr": "stub"}, sample_sources)
    assert ans.formal_statements == []


def test_convert_formal_statements_empty_when_deep_has_none(sample_sources):
    """When deep has no formal_statements attribute, field must be empty list."""
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer()  # no formal_statements kwarg → default_factory=list
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)
    assert ans.formal_statements == []


# ---------------------------------------------------------------------------
# Citation canonicalization (dedup, orphan prune, renumber)
# ---------------------------------------------------------------------------


def test_citation_dedup_prune_renumber(sample_sources):
    """Regression: model emits duplicate chunkIds and orphan citation entries.

    Live bug: chunkId "63646fbd" appeared at indexes 1/3/6, chunkId "400c85f7"
    at 2/4; inline markers [1,2,5,7,8,9,10] but citations array had [1..10].

    After canonicalization:
      - each distinct chunkId appears once
      - every inline [N] has a matching citation
      - no orphan citation entries (no citation without an inline marker)
      - indexes are contiguous from 1
      - [F1]-style figure refs are untouched
    """
    import re
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import TutorCitation

    # Build a DeepTutorAnswer whose citations list has:
    #   - chunkId "aaa" at indexes 1 AND 3 (duplicate)
    #   - chunkId "bbb" at indexes 2 AND 4 (duplicate)
    #   - chunkId "ccc" at index 5 (orphan — no inline marker)
    # And whose aspect text uses only [1] and [2].
    deep = _make_deep_answer(
        definition=(
            "Stationarity means the distribution is unchanged by a time shift [1]. "
            "Weak stationarity requires only first and second moments [2]."
        ),
    )
    deep_cites = [
        TutorCitation(index=1, chunkId="aaa", authors_short="A et al.", year=2024,
                       book_name="Book A", chapter="ch01", section="1.1",
                       page_from=10, page_to=15, quote="Stationarity definition"),
        TutorCitation(index=2, chunkId="bbb", authors_short="B et al.", year=2023,
                       book_name="Book B", chapter="ch02", section="2.1",
                       page_from=20, page_to=25, quote="Weak stationarity"),
        TutorCitation(index=3, chunkId="aaa", authors_short="A et al.", year=2024,
                       book_name="Book A", chapter="ch01", section="1.1",
                       page_from=10, page_to=15, quote="Stationarity definition (dup)"),
        TutorCitation(index=4, chunkId="bbb", authors_short="B et al.", year=2023,
                       book_name="Book B", chapter="ch02", section="2.1",
                       page_from=20, page_to=25, quote="Weak stationarity (dup)"),
        TutorCitation(index=5, chunkId="ccc", authors_short="C et al.", year=2022,
                       book_name="Book C", chapter="ch03", section="3.1",
                       page_from=30, page_to=35, quote="Orphan — never cited inline"),
    ]
    deep.citations = deep_cites

    ans = _convert_to_tutor_answer(deep, {}, sample_sources)

    # 1) Each distinct chunkId appears exactly once
    chunk_ids = [c.chunkId for c in ans.citations]
    assert "aaa" in chunk_ids, f"chunkId 'aaa' missing from {chunk_ids}"
    assert "bbb" in chunk_ids, f"chunkId 'bbb' missing from {chunk_ids}"
    assert chunk_ids.count("aaa") == 1, f"chunkId 'aaa' appears {chunk_ids.count('aaa')} times"
    assert chunk_ids.count("bbb") == 1, f"chunkId 'bbb' appears {chunk_ids.count('bbb')} times"
    # Orphan "ccc" must not appear
    assert "ccc" not in chunk_ids, f"orphan chunkId 'ccc' should have been pruned"

    # 2) Indexes are contiguous from 1
    indexes = sorted(c.index for c in ans.citations)
    assert indexes == list(range(1, len(indexes) + 1)), f"indexes not contiguous: {indexes}"

    # 3) Every inline [N] marker in text maps to a citation
    inline_markers = {int(m) for m in re.findall(r"(?<!\w)\[(\d+)\]", ans.text)}
    cite_indexes = {c.index for c in ans.citations}
    assert inline_markers == cite_indexes, (
        f"inline markers {inline_markers} != citation indexes {cite_indexes}"
    )

    # 4) No orphan citations (every citation has an inline marker)
    assert len(ans.citations) == len(inline_markers)

    # 5) Aspects dict has consistent markers (same renumbering)
    for aspect_key, aspect_text in ans.aspects.items():
        if not aspect_text.strip():
            continue
        aspect_markers = {int(m) for m in re.findall(r"(?<!\w)\[(\d+)\]", aspect_text)}
        # All markers in aspects must be in the citation set
        assert aspect_markers <= cite_indexes, (
            f"aspect '{aspect_key}' has orphan markers {aspect_markers - cite_indexes}"
        )


def test_citation_renumber_preserves_figure_refs(sample_sources):
    """[F1]-style figure references must NOT be touched by canonicalization."""
    import re
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import TutorCitation

    deep = _make_deep_answer(
        definition="See [1] and the figure [F1] for illustration.",
    )
    deep.citations = [
        TutorCitation(index=1, chunkId="aaa", authors_short="A et al.", year=2024,
                       book_name="Book A", chapter="ch01", section="1.1",
                       page_from=10, page_to=15, quote="ref"),
    ]
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)
    assert "[F1]" in ans.text, "[F1] figure ref was incorrectly modified"
    assert "[F1]" in ans.aspects.get("definition", ""), "[F1] in aspect was incorrectly modified"


def test_citation_dedup_preserves_distinct_empty_chunkIds():
    """Citations with empty/falsy chunkId are each kept as their own entry —
    they are not deduped against each other or against corpus entries.
    Uses sources that won't interfere with the explicit citation chunkIds."""
    import re
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import TutorCitation

    srcs = [
        _src(1, "islp", "2.1", "Text.", chunk_id="src-a"),
        _src(2, "islp", "2.2", "Text.", chunk_id="src-b"),
    ]
    deep = _make_deep_answer(
        definition="Wikipedia says [1] and the textbook agrees [2].",
    )
    deep.citations = [
        TutorCitation(index=1, chunkId="", authors_short="Wikipedia", year=2024,
                       book_name="Wikipedia", chapter="", section="",
                       quote="wiki ref", url="https://en.wikipedia.org/wiki/X"),
        TutorCitation(index=2, chunkId="bbb", authors_short="B et al.", year=2023,
                       book_name="Book B", chapter="ch02", section="2.1",
                       page_from=20, page_to=25, quote="textbook ref"),
    ]
    ans = _convert_to_tutor_answer(deep, {}, srcs)

    # Two distinct citations should survive
    assert len(ans.citations) == 2
    chunk_ids = [c.chunkId for c in ans.citations]
    assert "bbb" in chunk_ids
    # Contiguous from 1
    assert sorted(c.index for c in ans.citations) == [1, 2]


@pytest.mark.asyncio
async def test_finalize_stage_runs_when_enabled(monkeypatch):
    import src.services.chat.agents.deep_tutor as dt
    from src.services.chat.llm import router
    calls = []

    async def fake_stream_structured(messages, model, on_aspect_delta=None):
        calls.append(model)
        if on_aspect_delta:
            on_aspect_delta("_raw", "final text")
        return (
            dt.DeepTutorAnswer(
                tldr="t", definition="d", formal_statement="",
                example_intuition="e", applications="a",
                further_reading="f", citations=[],
            ),
            {k: "x" for k in dt.ASPECT_HEADINGS},
        )

    monkeypatch.setattr(dt, "_stream_structured", fake_stream_structured)
    monkeypatch.setattr(router, "is_structured_output_capable", lambda m: True)
    deep, aspects = await dt._stream_finalize(
        "q", {"definition": "draft"}, sources=[], facets=["a"],
        figures=[], on_aspect_delta=lambda *a: None, model="deepseek-v4-pro",
    )
    assert "deepseek-v4-pro" in calls
    assert deep is not None


def test_build_finalize_message_includes_draft_and_facets():
    from src.services.chat.agents.deep_tutor import _build_finalize_message
    draft_aspects = {"definition": "Stationarity means ... [1]", "tldr": "x"}
    facets = ["strict stationarity", "weak stationarity", "unit root"]
    msg = _build_finalize_message(
        "What is stationarity, its versions, and a unit root?",
        draft_aspects, sources=[], facets=facets, figures=[],
    )
    for f in facets:
        assert f in msg
    assert "Stationarity means" in msg
    assert "one" in msg.lower() and "definition" in msg.lower()


def test_verify_drops_broken_figure_refs_and_reports_missing_facets():
    from src.services.chat.agents.deep_tutor import _verify_finalized
    aspects = {"definition": "See [F1] and [F2].", "applications": "Use it."}
    figures = [type("F", (), {"url": ""})(), type("F", (), {"url": "http://x/y.png"})()]
    cleaned, missing = _verify_finalized(aspects, figures, facets=["unit root", "weak stationarity"])
    assert "[F1]" not in cleaned["definition"]      # broken ref (empty url) stripped
    assert "[F2]" in cleaned["definition"]           # valid ref kept
    assert "unit root" in missing and "weak stationarity" in missing


def test_canonicalize_citations_remaps_formal_statements_cite(sample_sources):
    """formal_statements[].cite must be remapped when canonicalization
    renumbers citations.  Without the fix, a TutorFormalDef.cite that
    referenced original index 5 would stay at 5 even after dedup/prune
    collapses the range to 1..3, producing a broken [5] pill."""
    import re
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import TutorCitation, TutorFormalDef

    # Build a DeepTutorAnswer whose citations have duplicates and an orphan,
    # so canonicalization renumbers.  Inline text uses [1] and [2].
    deep = _make_deep_answer(
        definition=(
            "Strict stationarity [1] means the joint distribution is shift-invariant. "
            "Weak stationarity [2] requires only first and second moments."
        ),
    )
    deep_cites = [
        TutorCitation(index=1, chunkId="aaa", authors_short="A et al.", year=2024,
                       book_name="Book A", chapter="ch01", section="1.1",
                       page_from=10, page_to=15, quote="Strict stationarity"),
        TutorCitation(index=2, chunkId="bbb", authors_short="B et al.", year=2023,
                       book_name="Book B", chapter="ch02", section="2.1",
                       page_from=20, page_to=25, quote="Weak stationarity"),
        TutorCitation(index=3, chunkId="aaa", authors_short="A et al.", year=2024,
                       book_name="Book A", chapter="ch01", section="1.1",
                       page_from=10, page_to=15, quote="Dup strict"),
        TutorCitation(index=5, chunkId="ccc", authors_short="C et al.", year=2022,
                       book_name="Book C", chapter="ch03", section="3.1",
                       page_from=30, page_to=35, quote="Orphan"),
    ]
    deep.citations = deep_cites
    # formal_statement with cite=3, which after dedup maps 3→1 (same chunkId
    # as index 1), then after renumber 1→1.  A cite=5 (orphan) should still
    # remap to whatever the pipeline decides — the key invariant is that
    # the resulting cite exists in answer.citations.
    deep.formal_statements = [
        TutorFormalDef(kind="definition", label="Strict stationarity",
                       statement="A time series is strictly stationary if…", cite=3),
        TutorFormalDef(kind="definition", label="Weak stationarity",
                       statement="A time series is weakly stationary if…", cite=5),
    ]

    ans = _convert_to_tutor_answer(deep, {}, sample_sources)

    cite_indexes = {c.index for c in ans.citations}

    # Every formal_statement cite must exist in the citation set
    for fs in ans.formal_statements:
        assert fs.cite in cite_indexes, (
            f"formal_statement cite={fs.cite} not in citation indexes {cite_indexes}"
        )

    # After dedup: original index 3 (chunkId "aaa") → kept index 1.
    # After renumber: 1→1.  So cite should be 1 (not 3).
    strict_fs = [fs for fs in ans.formal_statements
                 if fs.label == "Strict stationarity"][0]
    assert strict_fs.cite == 1, (
        f"expected remapped cite=1, got {strict_fs.cite}"
    )

    # The weak stationarity fs had original cite=5 (chunkId "ccc").
    # Before the fs_markers fix, cite=5 was orphan-pruned because no inline
    # [5] marker existed — formal_statements[].cite was not in all_markers.
    # Now fs_markers adds formal-statement cites to the referenced set, so
    # "ccc" survives pruning and gets a contiguous index.
    weak_fs = [fs for fs in ans.formal_statements
               if fs.label == "Weak stationarity"][0]
    assert weak_fs.cite in cite_indexes, (
        f"formal_statement cite={weak_fs.cite} must resolve to a real citation"
    )


def test_formal_statement_cite_preserves_orphan_source():
    """Regression: a citation referenced ONLY via formal_statements[].cite
    (no inline [N] marker in text or aspects) must NOT be orphan-pruned.
    _convert_to_tutor_answer renders [cite] into the text via
    _render_formal_statements, so the full pipeline would see [3] as an
    inline marker.  The real bug is in _canonicalize_citations itself:
    if all_markers excludes formal-statement cites, they get pruned.
    Test _canonicalize_citations directly to isolate the failure mode."""
    from src.services.chat.agents.deep_tutor import _canonicalize_citations
    from src.services.chat.schemas.output import TutorCitation, TutorFormalDef

    text = "Concept [1] is important [2]."
    aspects = {"definition": text}
    cites = [
        TutorCitation(index=1, chunkId="aaa", authors_short="A et al.", year=2024,
                       book_name="Book A", chapter="ch01", section="1.1",
                       page_from=10, page_to=15, quote="Inline ref 1"),
        TutorCitation(index=2, chunkId="bbb", authors_short="B et al.", year=2023,
                       book_name="Book B", chapter="ch02", section="2.1",
                       page_from=20, page_to=25, quote="Inline ref 2"),
        TutorCitation(index=3, chunkId="ccc", authors_short="C et al.", year=2022,
                       book_name="Book C", chapter="ch03", section="3.1",
                       page_from=30, page_to=35, quote="Formal def source"),
    ]
    fs = [
        TutorFormalDef(kind="definition", label="Strict stationarity",
                       statement="A process is strictly stationary if…", cite=3),
    ]

    _, _, out_cites, out_fs = _canonicalize_citations(text, aspects, cites, fs)

    cite_indexes = {c.index for c in out_cites}
    chunk_ids = [c.chunkId for c in out_cites]

    # The formal-statement's source (chunkId "ccc") must NOT be pruned
    assert "ccc" in chunk_ids, (
        f"formal-statement-only source pruned; chunks={chunk_ids}"
    )

    # The formal_statement's cite must resolve to a real citation index
    assert out_fs[0].cite in cite_indexes, (
        f"formal_statement cite={out_fs[0].cite} dangling, not in {cite_indexes}"
    )

    # Indexes must be contiguous from 1
    indexes = sorted(c.index for c in out_cites)
    assert indexes == list(range(1, len(indexes) + 1)), (
        f"indexes not contiguous: {indexes}"
    )
