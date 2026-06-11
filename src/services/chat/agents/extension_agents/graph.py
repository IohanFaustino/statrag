"""Extension v2 pipeline — deterministic async orchestration.

Stage order: storyteller×N (parallel) → editor → miner×take (parallel) →
researcher×subject (threaded code) → writer×take (parallel) → binder →
judge (ONE bounded retry of miner→research→write for failed takes).

Entry point: :func:`run_pipeline`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from src.services.chat.schemas.output import StoryDigest, Take

from .binder import bind_citations
from .nodes import (TakeDraft, run_editor, run_judge, run_miner,
                    run_storyteller, run_writer)
from .research import Evidence, corpus_evidence, wiki_evidence

# Callable contract: (stage_key: str, label: str) → None
# Called synchronously on the pipeline thread; never awaited.
OnStage = Callable[[str, str], None]

_logger = logging.getLogger(__name__)


async def _research_subject(s, *, exclude_book: str, all_slugs: list[str],
                             seen_ids: set[str]) -> list[Evidence]:
    """Threaded corpus search (up to 3 queries) + one wiki lookup per subject.

    Wiki query strategy: try each of the subject's mined queries (up to 2)
    before falling back to the verbose subject title.  Mined queries are short,
    canonical terms ("weak law of large numbers") that Wikipedia resolves
    reliably; the title is often too long ("(application) Consistency vs. …").
    We stop at the first query that returns a hit so only ONE wiki Evidence
    object is produced per subject.
    """
    out: list[Evidence] = []
    for q in (s.queries or [s.title])[:3]:
        out += await asyncio.to_thread(
            corpus_evidence, q, subject_id=s.id, exclude_book=exclude_book,
            all_slugs=all_slugs, seen_ids=seen_ids, top_n=3)
    wiki_hits: list[Evidence] = []
    for q in [*(s.queries or [])[:2], s.title]:
        wiki_hits = await asyncio.to_thread(wiki_evidence, q, subject_id=s.id)
        if wiki_hits:
            break
    out += wiki_hits
    _logger.info("research subject=%r corpus=%d wiki=%d wiki_title=%r",
                 s.title[:60], len(out) - len(wiki_hits), len(wiki_hits),
                 wiki_hits[0].meta.get("title") if wiki_hits else None)
    return out


async def _box_for_takes(
    takes: list[TakeDraft], *,
    book: str,
    all_slugs: list[str],
    seen_ids: set[str],
    stage_models: dict | None,
    on_stage: OnStage,
) -> tuple[list, list[Evidence], list]:
    """miner → researcher → writer for the given takes.

    Returns:
        (bullets, evidence, subjects)
    """
    subj_lists = await asyncio.gather(
        *(run_miner(take=t, stage_models=stage_models) for t in takes))
    subjects = [s for lst in subj_lists for s in lst]

    on_stage("research", f"Researching {len(subjects)} subjects")
    ev_lists = await asyncio.gather(
        *(_research_subject(s, exclude_book=book, all_slugs=all_slugs,
                            seen_ids=seen_ids) for s in subjects))
    evidence = [e for lst in ev_lists for e in lst]

    # Partition evidence and subjects by take index.
    by_take_ev: dict[int, list[Evidence]] = {t.idx: [] for t in takes}
    by_take_sub: dict[int, list] = {t.idx: [] for t in takes}
    for s in subjects:
        by_take_sub[s.take_idx].append(s)
    # O(S+E) lookup: build subject_id → take_idx map once rather than scanning
    # subjects for every evidence item (the original O(S×E) next() call).
    sub_take: dict[str, int] = {s.id: s.take_idx for s in subjects}
    for e in evidence:
        tk = sub_take.get(e.subject_id)
        if tk is not None:
            by_take_ev[tk].append(e)

    on_stage("write", f"Curiosity boxes 0/{len(takes)}")
    bullet_lists = await asyncio.gather(
        *(run_writer(take_idx=t.idx, take_heading=t.heading, take_story=t.story,
                     subjects=by_take_sub[t.idx], evidence=by_take_ev[t.idx],
                     stage_models=stage_models) for t in takes))
    bullets = [b for lst in bullet_lists for b in lst]
    ev_kind = {e.id: e.kind for e in evidence}
    cited = [ev_kind.get(i, "?") for b in bullets for i in b.evidence_ids]
    _logger.info("write bullets=%d cited corpus=%d wiki=%d unknown=%d",
                 len(bullets), cited.count("corpus"), cited.count("wikipedia"),
                 cited.count("?"))
    return bullets, evidence, subjects


async def run_pipeline(
    *,
    book: str,
    chapter_label: str,
    sections: list[dict],
    all_slugs: list[str],
    stage_models: dict | None,
    on_stage: OnStage,
) -> tuple[StoryDigest, list[Evidence]]:
    """Run the full extension v2 pipeline and return a ``StoryDigest``.

    Args:
        book: slug of the source book (excluded from cross-corpus search).
        chapter_label: human-readable chapter scope string.
        sections: list of section dicts with keys ``section_id``, ``h2_path``,
            ``text`` (as produced by ``_section_to_dict`` in the runner).
        all_slugs: every known book slug (including *book*).
        stage_models: optional per-stage model overrides; ``None`` → all defaults.
        on_stage: synchronous callable ``(stage_key, label) → None`` used to
            emit progress events to the SSE wrapper.  Never awaited.

    Returns:
        ``(digest, evidence)`` where *evidence* is the flat list of all
        :class:`~.research.Evidence` objects collected during research (used by
        the SSE wrapper to emit ``sources_full``).
    """
    seen_ids: set[str] = set()

    # ── 1. storyteller fan-out (parallel) ──────────────────────────────────
    # prev_heading = h2_path of the preceding section for continuity context.
    drafts: list[TakeDraft] = list(await asyncio.gather(*(
        run_storyteller(
            idx=i,
            section=sec,
            prev_heading=(sections[i - 1].get("h2_path") if i else None),
            stage_models=stage_models,
        )
        for i, sec in enumerate(sections)
    )))
    for d in sorted(drafts, key=lambda d: d.idx):
        on_stage("story", f"Take {d.idx + 1}/{len(drafts)} — {d.heading}")

    # ── 2. editor ──────────────────────────────────────────────────────────
    on_stage("edit", "Stitch timeline")
    takes_d = await run_editor(drafts, stage_models)

    # ── 3-5. miner → researcher → writer ──────────────────────────────────
    bullets, evidence, subjects = await _box_for_takes(
        takes_d, book=book, all_slugs=all_slugs, seen_ids=seen_ids,
        stage_models=stage_models, on_stage=on_stage,
    )

    # ── 6. binder ─────────────────────────────────────────────────────────
    on_stage("bind", "Binding citations")
    bound, dropped = bind_citations(bullets, evidence)

    # ── 7. judge + ONE bounded retry for failed takes ──────────────────────
    on_stage("judge", "Coverage check")
    items_by_take: dict[int, list] = {}
    for tk, item in bound:
        items_by_take.setdefault(tk, []).append(item)

    unfilled: list[str] = list(dropped)
    failed_takes: list[TakeDraft] = []

    for t in takes_d:
        subs = [s.title for s in subjects if s.take_idx == t.idx]
        if not subs:
            continue
        summary = "\n".join(
            f"- {i.subject}: {i.body[:200]}"
            for i in items_by_take.get(t.idx, [])
        )
        failed = await run_judge(
            take_heading=t.heading, subjects=subs,
            bullets_summary=summary, stage_models=stage_models,
        )
        if failed:
            failed_takes.append(t)
            unfilled += failed

    if failed_takes:
        on_stage("judge", f"Retry round — {len(failed_takes)} takes")
        rb, rev, _ = await _box_for_takes(
            failed_takes, book=book, all_slugs=all_slugs, seen_ids=seen_ids,
            stage_models=stage_models, on_stage=on_stage,
        )
        rbound, rdropped = bind_citations(rb, rev)
        evidence = evidence + rev

        recovered_subjects: set[str] = set()
        for tk, item in rbound:
            items_by_take.setdefault(tk, []).append(item)
            recovered_subjects.add(item.subject)

        # Remove recovered subject titles from unfilled; append newly dropped.
        unfilled = [u for u in unfilled if u not in recovered_subjects] + rdropped

    takes = [
        Take(heading=d.heading, story=d.story, items=items_by_take.get(d.idx, []))
        for d in sorted(takes_d, key=lambda d: d.idx)
    ]
    digest = StoryDigest(
        book=book,
        chapter=chapter_label,
        takes=takes,
        unfilled_subjects=sorted(set(unfilled)),
    )
    return digest, evidence
