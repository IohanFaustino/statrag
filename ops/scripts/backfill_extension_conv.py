"""Backfill the lost assistant answer for extension conversation 9d9985d3…

The assistant answer was never persisted due to the pre-c8f52a3 GeneratorExit bug.
The answer content survives as agent-workspace artifacts:
  - curated/timeline.md        → curated points (titles + body prose)
  - footnotes/N.md             → individual footnote bodies (cleanest source)
  - footnotes/_final_output.md → ID/TITLE MAPPING (footnote id → topic title)

Usage:
    python ops/scripts/backfill_extension_conv.py                    # dry-run (default)
    python ops/scripts/backfill_extension_conv.py --apply            # write to DB
    python ops/scripts/backfill_extension_conv.py --apply --force    # replace existing row
    python ops/scripts/backfill_extension_conv.py --db path/to/other.db --apply
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Repo root + project imports
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from src.services.chat.schemas.output import (  # noqa: E402
    ExtensionDigest,
    ExtensionFootnote,
    ExtensionPoint,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONV_ID = "9d9985d3b1884fd7aafdf88a1afcaf6a"
BOOK = "hansen-probability"
CHAPTER = "ch07 · 7.4–7.5"

_ARTIFACTS_ROOT = _REPO_ROOT
_TIMELINE_FILE = _ARTIFACTS_ROOT / "curated" / "timeline.md"
_FOOTNOTES_DIR = _ARTIFACTS_ROOT / "footnotes"
_FINAL_OUTPUT = _FOOTNOTES_DIR / "_final_output.md"

# Footnote files that are bookkeeping noise (no useful body)
_SKIP_FOOTNOTE_STEMS = {"_coverage_check", "_final_output", "15_done_marker", "11_chebyshev_clt"}

# ---------------------------------------------------------------------------
# Pure parsing helpers (unit-testable, no side effects)
# ---------------------------------------------------------------------------


def parse_timeline(text: str) -> list[dict[str, str]]:
    """Parse a timeline markdown file into a list of {title, curated_text} dicts.

    Each ``## <Heading>`` starts a new point. The body is everything up to the
    next ``##`` heading (stripped of leading/trailing whitespace).

    Args:
        text: Raw markdown string from the timeline file.

    Returns:
        Ordered list of dicts with keys ``title`` and ``curated_text``.
    """
    points: list[dict[str, str]] = []
    # Split on lines that start a ## heading
    sections = re.split(r"(?m)^## ", text)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if title:
            points.append({"title": title, "curated_text": body})
    return points


def strip_leading_marker(body: str, marker: str) -> str:
    """Remove a leading ``N.`` or ``[N]`` marker duplicated in the body text.

    Some footnote files open with ``N. **Title**…`` or ``[N]`` where N is the
    numeric marker.  This duplication is cleaned here so the frontend does not
    render it twice.

    Args:
        body: Raw footnote body text.
        marker: The numeric marker string (e.g. ``"2"``).

    Returns:
        Body with the leading marker prefix removed (leading whitespace stripped).
    """
    stripped = body.lstrip()
    # Pattern: "N. " at start  OR  "[N]\n" at start  OR  "[N.N]\n"
    patterns = [
        rf"^\[{re.escape(marker)}\]\s*\n?",
        rf"^{re.escape(marker)}\.\s+",
    ]
    for pat in patterns:
        m = re.match(pat, stripped)
        if m:
            return stripped[m.end():].lstrip()
    return body


def extract_source_and_kind(body: str) -> tuple[str, str]:
    """Extract a source string and kind from a footnote body.

    Looks for patterns like:
      - ``**Source.** ...``
      - ``Source: ...``
      - ``(Wikipedia: URL)``
      - Bare ``https://...`` URL lines

    Sets ``kind="wikipedia"`` if the source references ``wikipedia.org``.

    Args:
        body: Full footnote body text.

    Returns:
        Tuple of (source_string, kind) where kind is ``"wikipedia"`` or
        ``"corpus"``.
    """
    # Pattern 1: **Source.** … (bold markdown source line)
    m = re.search(r"\*\*Source\.\*\*\s+(.+?)(?:\n|$)", body, re.DOTALL)
    if m:
        source = m.group(1).strip()
        kind = "wikipedia" if "wikipedia.org" in source else "corpus"
        return source, kind

    # Pattern 2: bare "Source." or "Source:" line (without bold)
    m = re.search(r"^Source[.:]?\s+(.+?)(?:\n|$)", body, re.MULTILINE)
    if m:
        source = m.group(1).strip()
        kind = "wikipedia" if "wikipedia.org" in source else "corpus"
        return source, kind

    # Pattern 3: (Wikipedia: URL)
    m = re.search(r"\(Wikipedia:\s*(https?://[^\)]+)\)", body)
    if m:
        return m.group(1).strip(), "wikipedia"

    # Pattern 4: lone https:// URL that references wikipedia
    m = re.search(r"https?://en\.wikipedia\.org/\S+", body)
    if m:
        return m.group(0).strip(), "wikipedia"

    # Pattern 5: any bare https:// URL
    m = re.search(r"https?://\S+", body)
    if m:
        return m.group(0).strip(), "corpus"

    return "recovered from agent workspace", "corpus"


def parse_id_title_mapping(text: str) -> dict[str, str]:
    """Parse the ID/TITLE MAPPING section from ``_final_output.md``.

    Format::

        N :: topic title

    Args:
        text: Full content of ``_final_output.md``.

    Returns:
        Dict mapping marker string (e.g. ``"2"``) to topic title.
    """
    mapping: dict[str, str] = {}
    in_mapping = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "ID/TITLE MAPPING":
            in_mapping = True
            continue
        if in_mapping:
            if stripped == "" and not mapping:
                continue  # skip blank lines before first entry
            if stripped.startswith("---") or stripped.startswith("FOOTNOTE"):
                break
            m = re.match(r"^(\d+)\s*::\s*(.+)$", stripped)
            if m:
                mapping[m.group(1)] = m.group(2).strip()
    return mapping


def _token_overlap(a: str, b: str) -> int:
    """Count shared word tokens between two strings (case-insensitive)."""
    tokens_a = set(re.findall(r"[a-zA-Z]{3,}", a.lower()))
    tokens_b = set(re.findall(r"[a-zA-Z]{3,}", b.lower()))
    return len(tokens_a & tokens_b)


def match_footnote_to_point(
    fn_title: str,
    points: list[dict[str, str]],
) -> int:
    """Return the index of the best-matching point for a footnote topic title.

    Matching is done by token overlap with point ``title`` first, then with
    ``curated_text``.  Returns -1 if no match is found with non-zero overlap.

    Args:
        fn_title: The footnote's topic title from the ID/TITLE MAPPING.
        points: List of point dicts with ``title`` and ``curated_text``.

    Returns:
        Index into ``points`` of the best match, or -1 if unmatched.
    """
    best_idx = -1
    best_score = 0
    for i, point in enumerate(points):
        score = _token_overlap(fn_title, point["title"]) * 2 + _token_overlap(
            fn_title, point["curated_text"]
        )
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx if best_score > 0 else -1


# ---------------------------------------------------------------------------
# Artifact loading helpers
# ---------------------------------------------------------------------------


class _FootnoteRaw(NamedTuple):
    marker: str
    body: str
    source: str
    kind: str


def _stem_to_marker(stem: str) -> str:
    """Convert a footnote filename stem to a dotted marker string.

    Rules:
    - Plain integer stem ``"4"`` → ``"4"``
    - Underscore-separated ``"4_2"`` → ``"4.2"``
    - Already-dotted ``"7.4.1"`` → ``"7.4.1"`` (unchanged)

    Args:
        stem: Filename stem (without ``.md`` extension).

    Returns:
        Dotted marker string used as the footnote's ``marker`` field.
    """
    return stem.replace("_", ".")


def _integer_prefix(stem: str) -> str | None:
    """Return the leading integer portion of a stem, or None if absent.

    Used to resolve an id_title_map lookup for compound stems whose full
    dotted marker has no own mapping entry (they inherit from their integer
    prefix, e.g. ``"7.4.1"`` inherits mapping id ``"7"``).

    Args:
        stem: Filename stem, possibly compound.

    Returns:
        The leading integer as a string (e.g. ``"7"``), or ``None``.
    """
    m = re.match(r"^(\d+)", stem)
    return m.group(1) if m else None


def _load_footnotes(footnotes_dir: Path, id_title_map: dict[str, str]) -> list[_FootnoteRaw]:
    """Load all useful footnote files from ``footnotes_dir``.

    Each non-skipped ``*.md`` file is treated as an independent footnote.
    The marker is the full dotted stem (underscores → dots), so ``4_2.md``
    becomes marker ``"4.2"``, ``7.4.1.md`` becomes ``"7.4.1"``, and plain
    ``4.md`` becomes ``"4"``.  No deduplication by leading integer is
    performed — every file with real content is kept.

    For id_title_map lookup, compound markers first try the full dotted stem
    as the key; if absent they fall back to the leading integer prefix (e.g.
    ``"7.4.1"`` falls back to ``"7"``).

    Args:
        footnotes_dir: Path to the footnotes directory.
        id_title_map: Mapping from marker to topic title (from
            ``_final_output.md``).  Compound stems inherit the integer-prefix
            mapping when the full stem has no own entry.

    Returns:
        List of ``_FootnoteRaw`` namedtuples, one per useful file, sorted by
        stem for deterministic order.
    """
    results: list[_FootnoteRaw] = []

    # Sort for deterministic order: plain integers before compound stems.
    files = sorted(footnotes_dir.glob("*.md"), key=lambda p: p.stem)

    for fpath in files:
        stem = fpath.stem
        if stem in _SKIP_FOOTNOTE_STEMS:
            continue

        raw_body = fpath.read_text(encoding="utf-8").strip()
        if not raw_body or raw_body.lower() in {"placeholder"}:
            continue

        # Must start with a digit to be a real footnote file.
        if not re.match(r"^\d", stem):
            continue

        marker = _stem_to_marker(stem)
        body = strip_leading_marker(raw_body, marker)
        source, kind = extract_source_and_kind(body)
        results.append(_FootnoteRaw(marker=marker, body=body, source=source, kind=kind))

    return results


# ---------------------------------------------------------------------------
# Assembly: combine timeline + footnotes → ExtensionDigest
# ---------------------------------------------------------------------------


def assemble_digest(
    timeline_text: str,
    footnotes_dir: Path,
    final_output_text: str,
    *,
    book: str = BOOK,
    chapter: str = CHAPTER,
) -> ExtensionDigest:
    """Assemble an ExtensionDigest from the on-disk artifacts.

    Args:
        timeline_text: Raw text of the chosen timeline file.
        footnotes_dir: Directory containing individual footnote ``.md`` files.
        final_output_text: Raw text of ``_final_output.md`` (for ID mapping).
        book: Book slug to stamp on the digest.
        chapter: Chapter label to stamp on the digest.

    Returns:
        A validated ``ExtensionDigest`` instance.
    """
    # 1. Parse timeline → ordered points
    raw_points = parse_timeline(timeline_text)

    # 2. Parse ID/TITLE mapping
    id_title_map = parse_id_title_mapping(final_output_text)

    # 3. Load footnotes
    footnote_raws = _load_footnotes(footnotes_dir, id_title_map)

    # 4. Build initial point structs (no footnotes yet)
    point_structs: list[dict] = [
        {"title": p["title"], "curated_text": p["curated_text"], "footnotes": []}
        for p in raw_points
    ]

    # 5. Attach each footnote to its best-matching point
    unmatched_footnotes: list[_FootnoteRaw] = []
    for fn in footnote_raws:
        # Look up title by full dotted marker first; fall back to integer prefix
        # for compound stems (e.g. "7.4.1" → try "7.4.1" then "7").
        fn_title = id_title_map.get(fn.marker, "")
        if not fn_title:
            int_prefix = fn.marker.split(".")[0]
            if int_prefix and int_prefix != fn.marker:
                fn_title = id_title_map.get(int_prefix, "")
        if fn_title:
            idx = match_footnote_to_point(fn_title, raw_points)
        else:
            # No mapping entry: match directly against point text
            idx = match_footnote_to_point(fn.marker, raw_points)

        if idx >= 0:
            point_structs[idx]["footnotes"].append(
                {"marker": fn.marker, "body": fn.body, "source": fn.source, "kind": fn.kind}
            )
        else:
            unmatched_footnotes.append(fn)

    # 6. If any unmatched, collect into a catch-all trailing point
    if unmatched_footnotes:
        point_structs.append(
            {
                "title": "Additional recovered footnotes",
                "curated_text": (
                    "Footnotes recovered from the agent workspace that could not be "
                    "matched to a section."
                ),
                "footnotes": [
                    {
                        "marker": fn.marker,
                        "body": fn.body,
                        "source": fn.source,
                        "kind": fn.kind,
                    }
                    for fn in unmatched_footnotes
                ],
            }
        )

    # 7. Build and validate via Pydantic
    extension_points = [
        ExtensionPoint(
            title=ps["title"],
            curated_text=ps["curated_text"],
            footnotes=[
                ExtensionFootnote(
                    marker=fn["marker"],
                    body=fn["body"],
                    source=fn["source"],
                    kind=fn["kind"],
                )
                for fn in ps["footnotes"]
            ],
        )
        for ps in point_structs
    ]

    return ExtensionDigest(
        book=book,
        chapter=chapter,
        points=extension_points,
        unfilled_gaps=[],
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _read_user_timestamp(db_path: Path) -> str | None:
    """Return the timestamp of the user message in CONV_ID, or None."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT timestamp FROM messages WHERE conversation_id=? AND role='user' LIMIT 1",
            (CONV_ID,),
        ).fetchone()
        return row["timestamp"] if row else None
    finally:
        conn.close()


def _assistant_exists(db_path: Path) -> bool:
    """Return True if an assistant message already exists for CONV_ID."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id FROM messages WHERE conversation_id=? AND role='assistant' LIMIT 1",
            (CONV_ID,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _delete_assistant_messages(db_path: Path) -> int:
    """Delete all assistant messages for CONV_ID. Returns the number of rows deleted."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.execute(
            "DELETE FROM messages WHERE conversation_id=? AND role='assistant'",
            (CONV_ID,),
        )
        count = cursor.rowcount
        conn.commit()
        return count
    finally:
        conn.close()


def _insert_assistant_message(
    db_path: Path,
    digest: ExtensionDigest,
    user_timestamp: str,
) -> str:
    """Insert the assistant message row. Returns the new message id."""
    # Compute timestamp ~60s after the user message
    try:
        user_dt = datetime.fromisoformat(user_timestamp)
    except ValueError:
        user_dt = datetime.now(timezone.utc)
    assist_dt = user_dt + timedelta(seconds=60)
    timestamp = assist_dt.isoformat()

    msg_id = uuid.uuid4().hex

    # Build content JSON matching the frontend's expected shape
    content_obj = digest.model_dump()
    content_obj["_schema"] = "ExtensionDigest"
    content_str = json.dumps(content_obj, ensure_ascii=False)

    metadata_str = json.dumps({"turnMode": "extension"})

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """INSERT INTO messages
               (id, conversation_id, role, content, sources, figures, metadata, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg_id,
                CONV_ID,
                "assistant",
                content_str,
                "[]",
                None,
                metadata_str,
                timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return msg_id


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_summary(digest: ExtensionDigest, *, verbose: bool = False) -> None:
    """Print a human-readable dry-run summary."""
    total_footnotes = sum(len(p.footnotes) for p in digest.points)
    print(f"\n=== Dry-run summary ===")
    print(f"Book:    {digest.book}")
    print(f"Chapter: {digest.chapter}")
    print(f"Points:  {len(digest.points)}")
    print(f"Footnotes (total): {total_footnotes}")
    print(f"Unfilled gaps: {len(digest.unfilled_gaps)}")
    print()
    print("Per-point footnote distribution:")
    for i, p in enumerate(digest.points, 1):
        fn_markers = [fn.marker for fn in p.footnotes]
        print(f"  {i:2}. {p.title[:70]!r}  →  {len(p.footnotes)} footnotes {fn_markers}")
    if verbose:
        print()
        print("=== Full digest JSON ===")
        print(json.dumps(digest.model_dump(), ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Entry point for the backfill script."""
    parser = argparse.ArgumentParser(
        description="Backfill lost extension assistant answer from agent workspace artifacts."
    )
    parser.add_argument(
        "--db",
        default=str(_REPO_ROOT / "data" / "chat.db"),
        help="Path to chat.db (default: data/chat.db relative to repo root)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write the assembled message to the DB (default: dry-run only)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="In dry-run mode, also print the full digest JSON",
    )
    parser.add_argument(
        "--timeline",
        default=str(_TIMELINE_FILE),
        help="Path to the timeline markdown file to use as curated-text source",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "With --apply: if an assistant message already exists, back up the DB, "
            "delete the existing row(s), and insert the freshly assembled one. "
            "Has no effect without --apply."
        ),
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    timeline_path = Path(args.timeline)

    # --- Validate input paths ---
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    if not timeline_path.exists():
        print(f"ERROR: Timeline file not found at {timeline_path}", file=sys.stderr)
        sys.exit(1)
    if not _FINAL_OUTPUT.exists():
        print(f"ERROR: _final_output.md not found at {_FINAL_OUTPUT}", file=sys.stderr)
        sys.exit(1)

    # --- Idempotency check (before artifact assembly) ---
    already_exists = _assistant_exists(db_path)
    if already_exists:
        if not args.apply:
            if args.force:
                print(
                    f"NOTE: assistant message already present — "
                    f"--apply --force would replace it."
                )
            else:
                print(
                    f"NOTE: assistant message already present — "
                    f"--apply would abort (use --apply --force to replace)."
                )
        elif not args.force:
            print(
                f"\nABORT: An assistant message already exists for conversation {CONV_ID}.\n"
                "No changes made (idempotent guard). Use --force to replace.",
                file=sys.stderr,
            )
            sys.exit(1)

    # --- Load artifacts ---
    timeline_text = timeline_path.read_text(encoding="utf-8")
    final_output_text = _FINAL_OUTPUT.read_text(encoding="utf-8")

    # --- Assemble digest ---
    print(f"Using timeline: {timeline_path}")
    digest = assemble_digest(
        timeline_text=timeline_text,
        footnotes_dir=_FOOTNOTES_DIR,
        final_output_text=final_output_text,
    )

    # --- Print summary ---
    _print_summary(digest, verbose=args.verbose)

    if not args.apply:
        print("\nDRY RUN — pass --apply to write to the database.")
        return

    # --- Backup DB ---
    utc_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.parent / f"{db_path.name}.bak-{utc_stamp}"
    shutil.copy2(str(db_path), str(backup_path))
    print(f"\nDB backed up to: {backup_path}")

    # --- Force-replace: delete existing row(s) ---
    if already_exists and args.force:
        deleted = _delete_assistant_messages(db_path)
        print(f"Deleted {deleted} existing assistant row(s) for conversation {CONV_ID}.")

    # --- Read user timestamp ---
    user_ts = _read_user_timestamp(db_path)
    if user_ts is None:
        print(
            f"ERROR: No user message found for conversation {CONV_ID} in {db_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"User message timestamp: {user_ts}")

    # --- Insert ---
    msg_id = _insert_assistant_message(db_path, digest, user_ts)
    print(f"\nInserted assistant message: id={msg_id}")
    print("Done.")


if __name__ == "__main__":
    main()
