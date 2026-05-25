"""Author-perspective diversity step for the deep-tutor retrieval pipeline.

This module implements a round-robin author diversification pass over the
ranked section keys produced by the density-scoring stage, plus an optional
stratified fill that targets under-represented authors via filtered Qdrant
queries.

Algorithm overview (``diversify_section_keys``)
------------------------------------------------
Input: ``scored_keys`` — section (book, section) tuples already sorted by
descending relevance; ``key_meta`` — per-key metadata (author, year, score);
``target_authors`` — number of distinct author groups to aim for;
``top_sections`` — total slots to fill.

1. **Build author queues** — group keys by their normalized author identity
   (see ``author_key``).  Within each group, keys are already relevance-sorted
   so the first element is the best for that author.

2. **Round-robin pass** — iterate over distinct-author queues in order of
   their best relevance score (so the globally best author goes first).
   In each round, advance to the next author and take its best remaining
   section.  Continue until ``top_sections`` slots are filled or all queues
   are exhausted.

3. **Extra-slot tiebreak by year spread** — once a second pick is needed
   from an author already represented, prefer the key whose year differs most
   from the years already picked for that author (maximises temporal spread
   across editions).

Properties:
- Deterministic and pure (no I/O, no randomness).
- When ``target_authors < 2`` the function returns a plain ``[:top_sections]``
  slice, preserving the existing behaviour exactly.
- When fewer than ``target_authors`` distinct authors are available in
  ``scored_keys`` the function gracefully saturates with what it has.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import NamedTuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def author_key(src_or_meta: "AuthorMeta | _SrcLike") -> str:  # noqa: F821
    """Normalised author identity string for grouping / display.

    Priority: ``authors_short`` > ``authors`` > ``book``.
    Stripped and lower-cased so minor formatting differences don't fragment
    the same author into two groups.
    """
    # Accept either an AuthorMeta namedtuple or a Source-like object.
    if isinstance(src_or_meta, AuthorMeta):
        short = src_or_meta.authors_short or ""
        full  = src_or_meta.authors or ""
        book  = src_or_meta.book or ""
    else:
        short = getattr(src_or_meta, "authors_short", "") or ""
        full  = getattr(src_or_meta, "authors", "") or ""
        book  = getattr(src_or_meta, "book", "") or ""
    raw = short or full or book
    return raw.strip().lower()


class AuthorMeta(NamedTuple):
    """Compact per-section metadata used by the diversity algorithm."""
    authors_short: str
    authors: str
    book: str
    year: int | None
    score: float  # max density score for the section


def diversify_section_keys(
    scored_keys: list[tuple[str, str]],
    key_meta: dict[tuple[str, str], AuthorMeta],
    target_authors: int,
    top_sections: int,
) -> list[tuple[str, str]]:
    """Pick ``top_sections`` keys spanning up to ``target_authors`` distinct
    author groups via round-robin.

    Args:
        scored_keys: Section keys ``(book_slug, section_id)`` sorted by
            descending relevance (highest first).  This is the full ranked
            list from the density stage, before any ``[:top_sections]`` slice.
        key_meta: Metadata per key.  Keys not found here are treated as an
            unknown author (they are still eligible but grouped together under
            the empty-string author identity).
        target_authors: Desired number of distinct author groups in the
            result.  Values < 2 cause an immediate ``scored_keys[:top_sections]``
            return.
        top_sections: Number of slots to fill.

    Returns:
        A list of at most ``top_sections`` keys, ordered so the first
        ``min(target_authors, available_authors)`` entries each come from a
        different author (round-robin), followed by additional sections using
        a year-spread tiebreak.
    """
    if target_authors < 2:
        return scored_keys[:top_sections]

    if not scored_keys:
        return []

    # -- Step 1: group keys by author identity, preserve intra-group order ----
    # We want author queues ordered by their best-section relevance score so
    # the first round-robin picks the globally best author.
    author_queues: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in scored_keys:
        meta = key_meta.get(key)
        if meta is None:
            akey = ""
        else:
            akey = author_key(meta)
        author_queues[akey].append(key)

    # Sort distinct authors by their first (best) section score, descending.
    sorted_authors: list[str] = sorted(
        author_queues.keys(),
        key=lambda a: key_meta.get(author_queues[a][0], AuthorMeta("", "", "", None, 0.0)).score,
        reverse=True,
    )

    # -- Step 2: round-robin fill ---------------------------------------------
    result: list[tuple[str, str]] = []
    # Track which years we've already taken per author (for year-spread tiebreak).
    author_years_picked: dict[str, list[int | None]] = defaultdict(list)

    # Queue pointers — each author starts at index 0.
    queue_idx: dict[str, int] = {a: 0 for a in sorted_authors}

    # We iterate in rounds over the author list until we have top_sections.
    # In each pass we cycle through *all* authors (not just target_authors)
    # so we can fill remaining slots after the first round.
    rounds = 0
    max_rounds = top_sections + 1  # safety upper bound

    while len(result) < top_sections and rounds < max_rounds:
        rounds += 1
        made_progress = False
        for author in sorted_authors:
            if len(result) >= top_sections:
                break
            queue = author_queues[author]
            idx = queue_idx[author]
            if idx >= len(queue):
                continue  # this author is exhausted

            # For a 2nd+ pick from the same author, apply year-spread tiebreak:
            # scan forward in the queue for a key with a different year.
            if author in {author_key(AuthorMeta(**_am._asdict())) for _am in
                          [key_meta[r] for r in result if r in key_meta]
                          if author_key(_am) == author}:
                # already have at least one section from this author; look for
                # a year we haven't used yet.
                picked_years = set(author_years_picked[author])
                best_idx: int | None = None
                for j in range(idx, len(queue)):
                    candidate_key = queue[j]
                    m = key_meta.get(candidate_key)
                    yr = m.year if m else None
                    if yr not in picked_years:
                        best_idx = j
                        break
                if best_idx is None:
                    best_idx = idx  # no year diversity available; take next best
                # Swap to front of remaining range so queue_idx advances cleanly.
                if best_idx != idx:
                    queue[idx], queue[best_idx] = queue[best_idx], queue[idx]

            chosen_key = queue[idx]
            queue_idx[author] = idx + 1
            result.append(chosen_key)
            m = key_meta.get(chosen_key)
            author_years_picked[author].append(m.year if m else None)
            made_progress = True

        if not made_progress:
            break  # all queues exhausted

    return result


# ---------------------------------------------------------------------------
# Stratified fill helper (plan B)
# ---------------------------------------------------------------------------

def build_author_filter_from_candidates(
    query_authors_to_exclude: set[str],
    candidates: "list[Any]",  # list[Source]
) -> "list[Any]":  # list[Source]
    """From *candidates*, return only those whose author_key is NOT in
    *query_authors_to_exclude*.

    Used by the stratified-fill step to cheaply find sections from
    under-represented authors without a second Qdrant round-trip.
    """
    out = []
    for src in candidates:
        akey = author_key(src)
        if akey not in query_authors_to_exclude:
            out.append(src)
    return out
