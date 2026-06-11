"""End-to-end pipeline test with all LLM + retrieval boundaries mocked."""
import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.agents.extension_agents.binder import BulletDraft
from src.services.chat.agents.extension_agents.graph import run_pipeline
from src.services.chat.agents.extension_agents.nodes import Subject, TakeDraft
from src.services.chat.agents.extension_agents.research import Evidence

SECTIONS = [{"section_id": "7.4", "h2_path": "7.4 Chebyshev", "text": "AAA"},
            {"section_id": "7.5", "h2_path": "7.5 WLLN", "text": "BBB"}]


def _patches():
    return [
        patch("src.services.chat.agents.extension_agents.graph.run_storyteller",
              AsyncMock(side_effect=lambda *, idx, section, prev_heading, stage_models:
                        TakeDraft(idx=idx, heading=section["h2_path"], story=f"story {idx}"))),
        patch("src.services.chat.agents.extension_agents.graph.run_editor",
              AsyncMock(side_effect=lambda drafts, sm: sorted(drafts, key=lambda d: d.idx))),
        patch("src.services.chat.agents.extension_agents.graph.run_miner",
              AsyncMock(side_effect=lambda *, take, stage_models:
                        [Subject(id=f"t{take.idx}-s0", take_idx=take.idx,
                                 title=f"subj {take.idx}", queries=["q"])])),
        patch("src.services.chat.agents.extension_agents.graph.corpus_evidence",
              lambda *a, **k: []),
        patch("src.services.chat.agents.extension_agents.graph.wiki_evidence",
              lambda q, *, subject_id: [Evidence(id="e1", subject_id=subject_id,
                                                 kind="wikipedia", text="…",
                                                 meta={"title": "T", "url": "https://w/X"})]),
        patch("src.services.chat.agents.extension_agents.graph.run_writer",
              AsyncMock(side_effect=lambda *, take_idx, take_heading, take_story,
                        subjects, evidence, stage_models:
                        [BulletDraft(take_idx=take_idx, subject=subjects[0].title,
                                     body="body", evidence_ids=[evidence[0].id])]
                        if subjects and evidence else [])),
        patch("src.services.chat.agents.extension_agents.graph.run_judge",
              AsyncMock(return_value=[])),
    ]


@pytest.mark.asyncio
async def test_pipeline_produces_story_digest_with_bound_citations():
    """Happy path: 2 sections → StoryDigest with bound wikipedia citations."""
    stages: list[str] = []
    with contextlib.ExitStack() as st:
        for p in _patches():
            st.enter_context(p)
        digest, evidence = await run_pipeline(
            book="hansen-probability", chapter_label="ch07 · 7.4–7.5",
            sections=SECTIONS, all_slugs=["hansen-probability", "moss"],
            stage_models=None, on_stage=lambda k, lbl: stages.append(k))

    assert digest.book == "hansen-probability"
    assert [t.heading for t in digest.takes] == ["7.4 Chebyshev", "7.5 WLLN"]
    assert digest.takes[0].items[0].citations[0].kind == "wikipedia"
    assert digest.unfilled_subjects == []
    assert "story" in stages and "bind" in stages and "judge" in stages
    assert all(e.kind == "wikipedia" for e in evidence)


@pytest.mark.asyncio
async def test_pipeline_take_without_evidence_gets_empty_box_and_unfilled_subject():
    """When corpus+wiki both return [] and writer returns [], subject ends in unfilled_subjects."""
    stages: list[str] = []

    # Subject title for the single take/subject
    subject_title = "formal definition"

    # Judge returns the subject title on first (and only) call to mark it as failed.
    # Retry round: miner again returns a subject but corpus+wiki still empty → writer []
    # → binder drops it → subject stays in unfilled after retry too.
    # No infinite loop: retry is bounded to ONE round.
    miner_call_count = 0

    async def _miner(*, take, stage_models):
        nonlocal miner_call_count
        miner_call_count += 1
        return [Subject(id=f"t{take.idx}-s0", take_idx=take.idx,
                        title=subject_title, queries=["q"])]

    async def _writer(*, take_idx, take_heading, take_story,
                      subjects, evidence, stage_models):
        # Always empty — no evidence available
        return []

    judge_call_count = 0

    async def _judge(*, take_heading, subjects, bullets_summary, stage_models):
        nonlocal judge_call_count
        judge_call_count += 1
        # First judge call: report the subject as failed (triggers retry round)
        return [subject_title]

    patches = [
        patch("src.services.chat.agents.extension_agents.graph.run_storyteller",
              AsyncMock(side_effect=lambda *, idx, section, prev_heading, stage_models:
                        TakeDraft(idx=idx, heading=section["h2_path"], story=f"story {idx}"))),
        patch("src.services.chat.agents.extension_agents.graph.run_editor",
              AsyncMock(side_effect=lambda drafts, sm: sorted(drafts, key=lambda d: d.idx))),
        patch("src.services.chat.agents.extension_agents.graph.run_miner",
              AsyncMock(side_effect=_miner)),
        patch("src.services.chat.agents.extension_agents.graph.corpus_evidence",
              lambda *a, **k: []),
        patch("src.services.chat.agents.extension_agents.graph.wiki_evidence",
              lambda q, *, subject_id: []),
        patch("src.services.chat.agents.extension_agents.graph.run_writer",
              AsyncMock(side_effect=_writer)),
        patch("src.services.chat.agents.extension_agents.graph.run_judge",
              AsyncMock(side_effect=_judge)),
    ]

    with contextlib.ExitStack() as st:
        for p in patches:
            st.enter_context(p)
        digest, evidence = await run_pipeline(
            book="hansen-probability", chapter_label="ch07 · 7.4",
            sections=[SECTIONS[0]],
            all_slugs=["hansen-probability", "moss"],
            stage_models=None, on_stage=lambda k, lbl: stages.append(k))

    # No infinite loop: miner called exactly twice (once per round)
    assert miner_call_count == 2
    # Judge called once (the retry round does NOT re-judge per the plan)
    assert judge_call_count == 1
    # Take has no items
    assert digest.takes[0].items == []
    # Subject title is in unfilled_subjects
    assert subject_title in digest.unfilled_subjects


@pytest.mark.asyncio
async def test_pipeline_judge_retry_recovers_subject():
    """Retry round produces a bullet for the failed subject → NOT in unfilled_subjects."""
    subject_title = "derivation of bound"
    judge_called = 0

    async def _judge(*, take_heading, subjects, bullets_summary, stage_models):
        nonlocal judge_called
        judge_called += 1
        # First (and only) call: mark subject as failed → triggers retry
        return [subject_title]

    # Retry round writer returns a valid bullet with a wiki evidence id
    retry_wiki_ev = Evidence(id="e-retry", subject_id="t0-s0", kind="wikipedia",
                             text="retry text",
                             meta={"title": "Retry Article", "url": "https://w/retry"})

    retry_call_count = 0

    async def _writer(*, take_idx, take_heading, take_story,
                      subjects, evidence, stage_models):
        nonlocal retry_call_count
        retry_call_count += 1
        # First call (main round): no evidence → return []
        # Second call (retry round): evidence present → return a bullet
        if evidence:
            return [BulletDraft(take_idx=take_idx, subject=subjects[0].title,
                                body="recovered body", evidence_ids=[evidence[0].id])]
        return []

    main_wiki_called = 0
    retry_wiki_called = 0

    def _wiki(q, *, subject_id):
        nonlocal main_wiki_called, retry_wiki_called
        # There is one subject, so one wiki call per round.
        # First call is the main round; second call is the retry round — provide evidence then
        if retry_call_count == 0:
            # Still in main round (writer not yet called for retry)
            main_wiki_called += 1
            return []
        else:
            retry_wiki_called += 1
            ev = Evidence(id="e-retry", subject_id=subject_id, kind="wikipedia",
                          text="retry text",
                          meta={"title": "Retry Article", "url": "https://w/retry"})
            return [ev]

    patches = [
        patch("src.services.chat.agents.extension_agents.graph.run_storyteller",
              AsyncMock(side_effect=lambda *, idx, section, prev_heading, stage_models:
                        TakeDraft(idx=idx, heading=section["h2_path"], story=f"story {idx}"))),
        patch("src.services.chat.agents.extension_agents.graph.run_editor",
              AsyncMock(side_effect=lambda drafts, sm: sorted(drafts, key=lambda d: d.idx))),
        patch("src.services.chat.agents.extension_agents.graph.run_miner",
              AsyncMock(side_effect=lambda *, take, stage_models:
                        [Subject(id=f"t{take.idx}-s0", take_idx=take.idx,
                                 title=subject_title, queries=["q"])])),
        patch("src.services.chat.agents.extension_agents.graph.corpus_evidence",
              lambda *a, **k: []),
        patch("src.services.chat.agents.extension_agents.graph.wiki_evidence",
              side_effect=_wiki),
        patch("src.services.chat.agents.extension_agents.graph.run_writer",
              AsyncMock(side_effect=_writer)),
        patch("src.services.chat.agents.extension_agents.graph.run_judge",
              AsyncMock(side_effect=_judge)),
    ]

    with contextlib.ExitStack() as st:
        for p in patches:
            st.enter_context(p)
        digest, evidence = await run_pipeline(
            book="hansen-probability", chapter_label="ch07 · 7.4",
            sections=[SECTIONS[0]],
            all_slugs=["hansen-probability", "moss"],
            stage_models=None, on_stage=lambda k, lbl: None)

    # Judge called only once (retry round does NOT re-judge)
    assert judge_called == 1
    # Subject recovered: NOT in unfilled_subjects
    assert subject_title not in digest.unfilled_subjects
    # Item present on the take
    assert len(digest.takes[0].items) == 1
    assert digest.takes[0].items[0].subject == subject_title


@pytest.mark.asyncio
async def test_research_subject_uses_mined_queries_before_title():
    """wiki_evidence is called with mined queries first; stops at first hit.

    Setup: subject has queries=["weak law of large numbers", "convergence"].
    Mock: wiki returns [] for "weak law of large numbers", a hit for
    "convergence", and should NOT be called with the verbose title at all.
    Assert:
      - wiki_evidence called exactly 2 times (stops after second query hits).
      - The Evidence from the second query appears in the pipeline output.
    """
    from src.services.chat.agents.extension_agents.graph import _research_subject

    hit_ev = Evidence(
        id="wiki-hit", subject_id="t0-s0", kind="wikipedia",
        text="Convergence article text",
        meta={"title": "Convergence (probability)", "url": "https://en.wikipedia.org/wiki/Convergence"},
    )
    wiki_call_queries: list[str] = []

    def _wiki(q: str, *, subject_id: str) -> list[Evidence]:
        wiki_call_queries.append(q)
        if q == "convergence":
            return [Evidence(
                id=hit_ev.id, subject_id=subject_id, kind=hit_ev.kind,
                text=hit_ev.text, meta=hit_ev.meta,
            )]
        return []

    subj = Subject(
        id="t0-s0", take_idx=0,
        title="(application) Consistency vs. Rates: Why WLLN Doesn't Tell You How Large n Must Be",
        queries=["weak law of large numbers", "convergence"],
    )

    with contextlib.ExitStack() as st:
        st.enter_context(patch(
            "src.services.chat.agents.extension_agents.graph.corpus_evidence",
            lambda *a, **k: [],
        ))
        st.enter_context(patch(
            "src.services.chat.agents.extension_agents.graph.wiki_evidence",
            side_effect=_wiki,
        ))
        result = await _research_subject(
            subj,
            exclude_book="hansen-probability",
            all_slugs=["hansen-probability"],
            seen_ids=set(),
        )

    # Stopped after second query — verbose title never tried
    assert wiki_call_queries == ["weak law of large numbers", "convergence"], (
        f"expected 2 calls (stop at first hit), got: {wiki_call_queries}"
    )
    # The hit evidence is present in the output
    wiki_results = [e for e in result if e.kind == "wikipedia"]
    assert len(wiki_results) == 1
    assert wiki_results[0].id == hit_ev.id


@pytest.mark.asyncio
async def test_research_subject_logs_per_subject_summary(caplog):
    """_research_subject emits an INFO log with corpus/wiki counts."""
    import logging
    from src.services.chat.agents.extension_agents.graph import _research_subject

    corpus_ev = Evidence(
        id="c1", subject_id="t0-s0", kind="corpus",
        text="corpus text", meta={"book": "hansen-probability"},
    )
    wiki_ev = Evidence(
        id="w1", subject_id="t0-s0", kind="wikipedia",
        text="wiki text", meta={"title": "LLN", "url": "https://en.wikipedia.org/wiki/LLN"},
    )

    subj = Subject(id="t0-s0", take_idx=0, title="Law of Large Numbers", queries=["LLN"])

    with caplog.at_level(logging.INFO, logger="src.services.chat.agents.extension_agents.graph"):
        with contextlib.ExitStack() as st:
            st.enter_context(patch(
                "src.services.chat.agents.extension_agents.graph.corpus_evidence",
                lambda *a, **k: [corpus_ev],
            ))
            st.enter_context(patch(
                "src.services.chat.agents.extension_agents.graph.wiki_evidence",
                lambda q, *, subject_id: [wiki_ev],
            ))
            await _research_subject(
                subj,
                exclude_book="hansen-probability",
                all_slugs=["hansen-probability"],
                seen_ids=set(),
            )

    # There must be at least one INFO record from the graph logger for this subject
    graph_records = [
        r for r in caplog.records
        if r.name == "src.services.chat.agents.extension_agents.graph"
        and r.levelno == logging.INFO
    ]
    assert graph_records, "Expected INFO log from _research_subject; got none"
    msg = graph_records[0].getMessage()
    # Message must contain corpus and wiki counts
    assert "corpus=" in msg
    assert "wiki=" in msg
