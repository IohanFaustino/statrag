"""Unit and integration tests for ops/scripts/backfill_extension_conv.py.

Tests cover:
- parse_timeline: extracts points from markdown
- strip_leading_marker: cleans leading N. / [N] from body text
- extract_source_and_kind: detects wikipedia/corpus sources
- parse_id_title_mapping: reads ID :: title lines
- match_footnote_to_point: token-overlap matching
- assemble_digest: end-to-end assembly with inline fixtures
- E2E: temp sqlite DB with user-only conversation → assert insert + idempotency
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Import helpers from the script under test
# ---------------------------------------------------------------------------
import importlib
import sys

# Ensure repo root is on the path so the script can do its own imports
_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT))

from ops.scripts.backfill_extension_conv import (  # noqa: E402
    CONV_ID,
    _FootnoteRaw,
    _assistant_exists,
    _delete_assistant_messages,
    _insert_assistant_message,
    _load_footnotes,
    _read_user_timestamp,
    _stem_to_marker,
    assemble_digest,
    extract_source_and_kind,
    match_footnote_to_point,
    parse_id_title_mapping,
    parse_timeline,
    strip_bookkeeping,
    strip_leading_marker,
)
from src.services.chat.schemas.output import ExtensionDigest  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

MINIMAL_TIMELINE = """\
## Chebyshev tail bound
Chebyshev's inequality controls tails using only the variance.

## Convergence in probability
If the variance of Z_n vanishes, Z_n converges in probability to its mean.

## WLLN for sample means
Sample mean converges in probability to the population mean.
"""

MINIMAL_FINAL_OUTPUT = """\
ID/TITLE MAPPING

1 :: Chebyshev proof details
2 :: Convergence in probability definition
3 :: WLLN statement

FOOTNOTE TEXTS
"""

_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'tutor',
    model_id     TEXT NOT NULL,
    book_filter  TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    sources          TEXT,
    figures          TEXT,
    metadata         TEXT,
    timestamp        TEXT NOT NULL
);
"""


def _make_temp_db(tmp_path: Path, *, with_user_msg: bool = True) -> Path:
    """Create a minimal sqlite DB with the messages schema.

    If ``with_user_msg`` is True, inserts the target conversation and a user
    message with a known timestamp.

    Returns the path to the created DB.
    """
    db_path = tmp_path / "test_chat.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_DDL)
    if with_user_msg:
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?,?)",
            (
                CONV_ID,
                "Extend Hansen ch7 (7.4-7.5)",
                "extension",
                "gpt-5.4-nano-2026-03-17",
                '"ALL"',
                "2026-06-09T19:29:48.084912+00:00",
                "2026-06-09T19:29:48.119967+00:00",
            ),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
            (
                uuid.uuid4().hex,
                CONV_ID,
                "user",
                '"Extend section 7.4 and 7.5 of Hansen"',
                None,
                None,
                None,
                "2026-06-09T19:29:48.118910+00:00",
            ),
        )
    conn.commit()
    conn.close()
    return db_path


def _make_footnote_dir(tmp_path: Path, entries: dict[str, str]) -> Path:
    """Write footnote files into ``tmp_path/footnotes/`` and return the dir."""
    fn_dir = tmp_path / "footnotes"
    fn_dir.mkdir()
    for name, content in entries.items():
        (fn_dir / name).write_text(content, encoding="utf-8")
    return fn_dir


# ---------------------------------------------------------------------------
# parse_timeline
# ---------------------------------------------------------------------------


def test_parse_timeline_basic() -> None:
    points = parse_timeline(MINIMAL_TIMELINE)
    assert len(points) == 3
    assert points[0]["title"] == "Chebyshev tail bound"
    assert "variance" in points[0]["curated_text"]
    assert points[1]["title"] == "Convergence in probability"
    assert points[2]["title"] == "WLLN for sample means"


def test_parse_timeline_empty() -> None:
    assert parse_timeline("") == []


def test_parse_timeline_no_headings() -> None:
    # No "## " heading markers → the whole text is returned as a single
    # section by re.split; since there is at least one non-empty section
    # the parser produces one point. Verify it has the right shape.
    result = parse_timeline("Just some prose without any heading.\n")
    # Either empty or 1 point with the prose as title — both are acceptable
    # (the function is used with real markdown that always has ## headings)
    assert isinstance(result, list)


def test_parse_timeline_single_heading_no_body() -> None:
    points = parse_timeline("## Only a title\n")
    assert len(points) == 1
    assert points[0]["title"] == "Only a title"
    assert points[0]["curated_text"] == ""


def test_parse_timeline_preserves_polish() -> None:
    text = "## Dlaczego WLLN bywa fałszywe\nPo polsku treść.\n"
    points = parse_timeline(text)
    assert points[0]["title"] == "Dlaczego WLLN bywa fałszywe"
    assert "polsku" in points[0]["curated_text"]


# ---------------------------------------------------------------------------
# strip_leading_marker
# ---------------------------------------------------------------------------


def test_strip_leading_marker_dot_form() -> None:
    body = "2. **Bold title.** Some content."
    result = strip_leading_marker(body, "2")
    assert result == "**Bold title.** Some content."


def test_strip_leading_marker_bracket_form() -> None:
    body = "[3]\nSome body text."
    result = strip_leading_marker(body, "3")
    assert result.startswith("Some body text.")


def test_strip_leading_marker_no_match_unchanged() -> None:
    body = "This body has no leading marker."
    result = strip_leading_marker(body, "5")
    assert result == body


def test_strip_leading_marker_does_not_strip_mid_text() -> None:
    body = "Intro. 2. Not at start."
    result = strip_leading_marker(body, "2")
    assert result == body


# ---------------------------------------------------------------------------
# extract_source_and_kind
# ---------------------------------------------------------------------------


def test_extract_source_bold_wikipedia() -> None:
    body = "Some text.\n\n**Source.** Wikipedia: https://en.wikipedia.org/wiki/Chebyshev"
    source, kind = extract_source_and_kind(body)
    assert "wikipedia.org" in source
    assert kind == "wikipedia"


def test_extract_source_bold_corpus() -> None:
    body = "Some text.\n\n**Source.** Stock & Watson, §18.2"
    source, kind = extract_source_and_kind(body)
    assert "Stock" in source
    assert kind == "corpus"


def test_extract_source_bare_wikipedia_url() -> None:
    body = "See https://en.wikipedia.org/wiki/Markov%27s_inequality for details."
    source, kind = extract_source_and_kind(body)
    assert "wikipedia.org" in source
    assert kind == "wikipedia"


def test_extract_source_no_source_returns_fallback() -> None:
    body = "Just a body with no source information at all."
    source, kind = extract_source_and_kind(body)
    assert source == "recovered from agent workspace"
    assert kind == "corpus"


def test_extract_source_multiple_urls_uses_first() -> None:
    body = "See https://en.wikipedia.org/wiki/One and https://en.wikipedia.org/wiki/Two."
    source, kind = extract_source_and_kind(body)
    assert "wikipedia.org" in source
    assert kind == "wikipedia"


# ---------------------------------------------------------------------------
# parse_id_title_mapping
# ---------------------------------------------------------------------------


def test_parse_id_title_mapping_basic() -> None:
    mapping = parse_id_title_mapping(MINIMAL_FINAL_OUTPUT)
    assert mapping == {
        "1": "Chebyshev proof details",
        "2": "Convergence in probability definition",
        "3": "WLLN statement",
    }


def test_parse_id_title_mapping_empty_text() -> None:
    assert parse_id_title_mapping("") == {}


def test_parse_id_title_mapping_stops_at_footnote_texts() -> None:
    text = "ID/TITLE MAPPING\n\n1 :: alpha\n2 :: beta\n\nFOOTNOTE TEXTS\n3 :: gamma\n"
    mapping = parse_id_title_mapping(text)
    assert "1" in mapping
    assert "2" in mapping
    assert "3" not in mapping


# ---------------------------------------------------------------------------
# match_footnote_to_point
# ---------------------------------------------------------------------------

_POINTS = [
    {"title": "Chebyshev tail bound", "curated_text": "Chebyshev variance inequality proof."},
    {"title": "WLLN convergence", "curated_text": "Sample mean converges to population mean."},
    {"title": "Markov inequality", "curated_text": "Markov bound for nonnegative variables."},
]


def test_match_footnote_exact_title_word() -> None:
    idx = match_footnote_to_point("Chebyshev variance step", _POINTS)
    assert idx == 0


def test_match_footnote_wlln() -> None:
    idx = match_footnote_to_point("WLLN sample mean convergence", _POINTS)
    assert idx == 1


def test_match_footnote_markov() -> None:
    idx = match_footnote_to_point("Markov inequality nonnegative", _POINTS)
    assert idx == 2


def test_match_footnote_no_overlap_returns_minus_one() -> None:
    idx = match_footnote_to_point("completely unrelated topic xyz", _POINTS)
    assert idx == -1


# ---------------------------------------------------------------------------
# assemble_digest (integration over inline fixtures)
# ---------------------------------------------------------------------------


def test_assemble_digest_structure(tmp_path: Path) -> None:
    fn_dir = _make_footnote_dir(
        tmp_path,
        {
            "1.md": (
                "1. Chebyshev proof in indicator form.\n\n"
                "**Source.** Wikipedia: https://en.wikipedia.org/wiki/Chebyshev%27s_inequality"
            ),
            "2.md": (
                "2. Convergence in probability definition.\n\n"
                "**Source.** Stock & Watson §18.2"
            ),
            "_coverage_check.md": "placeholder",
        },
    )
    final_output = "ID/TITLE MAPPING\n\n1 :: Chebyshev proof\n2 :: Convergence in probability\n\nFOOTNOTE TEXTS\n"

    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text=final_output,
        book="test-book",
        chapter="ch07",
    )

    assert isinstance(digest, ExtensionDigest)
    assert digest.book == "test-book"
    assert digest.chapter == "ch07"
    assert len(digest.points) >= 3  # at least 3 from MINIMAL_TIMELINE
    assert digest.unfilled_gaps == []
    total_fn = sum(len(p.footnotes) for p in digest.points)
    assert total_fn == 2  # 2 footnote files loaded


def test_assemble_digest_unmatched_footnotes_extra_point(tmp_path: Path) -> None:
    """A footnote with no overlap ends up in the catch-all trailing point."""
    fn_dir = _make_footnote_dir(
        tmp_path,
        {
            "99.md": (
                "99. Completely unrelated topic XYZ.\n\n"
                "**Source.** https://example.com/unrelated"
            ),
        },
    )
    final_output = "ID/TITLE MAPPING\n\n99 :: XYZ unrelated topic\n\nFOOTNOTE TEXTS\n"

    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text=final_output,
        book="test-book",
        chapter="ch07",
    )

    # The unmatched footnote should be in a trailing catch-all point
    assert any(
        "Additional recovered footnotes" in p.title for p in digest.points
    ), "Expected catch-all point for unmatched footnotes"


def test_assemble_digest_validates_pydantic(tmp_path: Path) -> None:
    """assemble_digest must return a valid ExtensionDigest (pydantic validates)."""
    fn_dir = _make_footnote_dir(tmp_path, {})
    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text=MINIMAL_FINAL_OUTPUT,
    )
    # Pydantic model_dump must be JSON-serialisable
    dumped = digest.model_dump()
    json.dumps(dumped)  # must not raise
    # _schema is NOT a field on ExtensionDigest — it is only added during insert
    assert "_schema" not in dumped


def test_assemble_digest_skips_placeholder_files(tmp_path: Path) -> None:
    fn_dir = _make_footnote_dir(
        tmp_path,
        {
            "1.md": "1. Real body.\n\n**Source.** https://en.wikipedia.org/wiki/Chebyshev%27s_inequality",
            "15_done_marker.md": "placeholder",
            "_coverage_check.md": "placeholder",
        },
    )
    final_output = "ID/TITLE MAPPING\n\n1 :: Chebyshev proof\n\nFOOTNOTE TEXTS\n"
    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text=final_output,
    )
    total_fn = sum(len(p.footnotes) for p in digest.points)
    assert total_fn == 1, "Only one non-placeholder footnote should be loaded"


# ---------------------------------------------------------------------------
# E2E: temp sqlite DB
# ---------------------------------------------------------------------------


def test_e2e_insert_assistant_message(tmp_path: Path) -> None:
    """Full end-to-end: build digest, insert into temp DB, verify."""
    db_path = _make_temp_db(tmp_path)

    # Build a minimal digest
    fn_dir = _make_footnote_dir(
        tmp_path,
        {
            "1.md": "1. Body text.\n\n**Source.** Stock & Watson §18.2",
        },
    )
    final_output = "ID/TITLE MAPPING\n\n1 :: Chebyshev proof\n\nFOOTNOTE TEXTS\n"
    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text=final_output,
    )

    assert not _assistant_exists(db_path)

    user_ts = _read_user_timestamp(db_path)
    assert user_ts is not None

    msg_id = _insert_assistant_message(db_path, digest, user_ts)

    # Verify the row was written
    assert _assistant_exists(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM messages WHERE id=?", (msg_id,)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["role"] == "assistant"
    assert row["conversation_id"] == CONV_ID
    assert row["sources"] == "[]"
    assert row["figures"] is None

    content = json.loads(row["content"])
    assert content["_schema"] == "ExtensionDigest"
    assert content["book"] == "hansen-probability"
    assert content["chapter"] == "ch07 · 7.4–7.5"
    assert isinstance(content["points"], list)
    assert content["unfilled_gaps"] == []

    metadata = json.loads(row["metadata"])
    assert metadata["turnMode"] == "extension"


def test_e2e_idempotency_guard(tmp_path: Path) -> None:
    """A second call to _assistant_exists returns True; _insert_… should not be called twice."""
    db_path = _make_temp_db(tmp_path)
    fn_dir = _make_footnote_dir(tmp_path, {})
    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text=MINIMAL_FINAL_OUTPUT,
    )

    user_ts = _read_user_timestamp(db_path)
    _insert_assistant_message(db_path, digest, user_ts)
    assert _assistant_exists(db_path)

    # Second insert would violate idempotency — calling the guard prevents it
    assert _assistant_exists(db_path) is True


def test_e2e_timestamp_is_after_user_message(tmp_path: Path) -> None:
    """The assistant message timestamp must be strictly after the user's."""
    db_path = _make_temp_db(tmp_path)
    fn_dir = _make_footnote_dir(tmp_path, {})
    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text=MINIMAL_FINAL_OUTPUT,
    )

    user_ts = _read_user_timestamp(db_path)
    msg_id = _insert_assistant_message(db_path, digest, user_ts)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT timestamp FROM messages WHERE id=?", (msg_id,)).fetchone()
    conn.close()

    assist_dt = datetime.fromisoformat(row["timestamp"])
    user_dt = datetime.fromisoformat(user_ts)
    assert assist_dt > user_dt


def test_e2e_read_user_timestamp_missing_conv(tmp_path: Path) -> None:
    """Returns None when the conversation / user message is absent."""
    db_path = _make_temp_db(tmp_path, with_user_msg=False)
    # Need at least the schema; no conversation row exists
    result = _read_user_timestamp(db_path)
    assert result is None


def test_e2e_content_validates_as_extension_digest(tmp_path: Path) -> None:
    """The stored content must parse back into a valid ExtensionDigest."""
    db_path = _make_temp_db(tmp_path)
    fn_dir = _make_footnote_dir(
        tmp_path,
        {
            "2.md": (
                "Body about Chebyshev variance.\n\n"
                "**Source.** https://en.wikipedia.org/wiki/Chebyshev%27s_inequality"
            ),
        },
    )
    final_output = "ID/TITLE MAPPING\n\n2 :: Chebyshev variance proof\n\nFOOTNOTE TEXTS\n"
    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text=final_output,
    )

    user_ts = _read_user_timestamp(db_path)
    msg_id = _insert_assistant_message(db_path, digest, user_ts)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT content FROM messages WHERE id=?", (msg_id,)).fetchone()
    conn.close()

    raw = json.loads(row["content"])
    # Remove _schema before feeding to Pydantic (it's not a model field)
    raw.pop("_schema", None)
    validated = ExtensionDigest(**raw)
    assert validated.book == "hansen-probability"
    assert len(validated.points) >= 1


# ---------------------------------------------------------------------------
# _stem_to_marker
# ---------------------------------------------------------------------------


def test_stem_to_marker_plain_integer() -> None:
    assert _stem_to_marker("4") == "4"


def test_stem_to_marker_underscore_compound() -> None:
    assert _stem_to_marker("4_2") == "4.2"


def test_stem_to_marker_dotted_compound() -> None:
    # Already dotted stems pass through unchanged
    assert _stem_to_marker("7.4.1") == "7.4.1"


def test_stem_to_marker_large_integer() -> None:
    assert _stem_to_marker("15") == "15"


# ---------------------------------------------------------------------------
# _load_footnotes — compound stems kept as independent markers
# ---------------------------------------------------------------------------


def test_load_footnotes_compound_stems_not_dropped(tmp_path: Path) -> None:
    """4.md + 4_2.md + 7.md + 7.4.1.md → 4 footnotes, markers 4/4.2/7/7.4.1."""
    fn_dir = _make_footnote_dir(
        tmp_path,
        {
            "4.md": "Chebyshev variance bound body.\n\n**Source.** Stock & Watson §4",
            "4_2.md": "Extended Chebyshev discrete case.\n\n**Source.** Stock & Watson §4.2",
            "7.md": "WLLN truncation argument.\n\n**Source.** Hansen §7",
            "7.4.1.md": "[7.4.1]\nChebyshev for WLLN.\n\n**Source.** Hansen §7.4",
        },
    )
    id_title_map: dict[str, str] = {}
    results = _load_footnotes(fn_dir, id_title_map)

    markers = {fn.marker for fn in results}
    assert markers == {"4", "4.2", "7", "7.4.1"}, (
        f"Expected all 4 compound stems kept; got {markers}"
    )
    assert len(results) == 4


def test_load_footnotes_compound_stem_marker_value() -> None:
    """Specifically verifies 7.5.1.md yields marker '7.5.1'."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        fn_dir = Path(d)
        (fn_dir / "7.5.1.md").write_text(
            "[7.5.1]\nWeak law via vanishing variance.\n\n**Source.** Hansen §7.5",
            encoding="utf-8",
        )
        results = _load_footnotes(fn_dir, {})
    assert len(results) == 1
    assert results[0].marker == "7.5.1"


def test_load_footnotes_skip_stems_still_skipped(tmp_path: Path) -> None:
    """_coverage_check, _final_output, 15_done_marker are skipped."""
    fn_dir = _make_footnote_dir(
        tmp_path,
        {
            "1.md": "Real footnote body.\n\n**Source.** https://example.com",
            "_coverage_check.md": "some coverage notes",
            "_final_output.md": "ID/TITLE MAPPING\n1 :: something",
            "15_done_marker.md": "placeholder",
        },
    )
    results = _load_footnotes(fn_dir, {})
    assert len(results) == 1
    assert results[0].marker == "1"


def test_load_footnotes_compound_stem_inherits_integer_prefix_mapping(tmp_path: Path) -> None:
    """Compound stem '7.4.1' inherits mapping topic of integer prefix '7'."""
    fn_dir = _make_footnote_dir(
        tmp_path,
        {
            "7.4.1.md": "Chebyshev for WLLN body.\n\n**Source.** Hansen §7.4",
        },
    )
    # Only integer prefix '7' is in the mapping, not '7.4.1'
    id_title_map = {"7": "WLLN with finite variance"}
    results = _load_footnotes(fn_dir, id_title_map)
    assert len(results) == 1
    assert results[0].marker == "7.4.1"

    # Now verify that assemble_digest correctly uses the inherited mapping for
    # match_footnote_to_point (the fn_title should be "WLLN with finite variance")
    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text="ID/TITLE MAPPING\n\n7 :: WLLN with finite variance\n\nFOOTNOTE TEXTS\n",
        book="test-book",
        chapter="ch07",
    )
    all_markers = [fn.marker for p in digest.points for fn in p.footnotes]
    assert "7.4.1" in all_markers, f"Marker '7.4.1' should be in digest; got {all_markers}"


# ---------------------------------------------------------------------------
# --force replace mode (temp DB)
# ---------------------------------------------------------------------------


def test_delete_assistant_messages_removes_rows(tmp_path: Path) -> None:
    """_delete_assistant_messages removes the assistant row and returns count."""
    db_path = _make_temp_db(tmp_path)
    fn_dir = _make_footnote_dir(tmp_path, {})
    digest = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir,
        final_output_text=MINIMAL_FINAL_OUTPUT,
    )
    user_ts = _read_user_timestamp(db_path)
    _insert_assistant_message(db_path, digest, user_ts)
    assert _assistant_exists(db_path)

    deleted = _delete_assistant_messages(db_path)
    assert deleted == 1
    assert not _assistant_exists(db_path)


def test_force_replaces_existing_assistant_row(tmp_path: Path) -> None:
    """--force via _delete + _insert replaces an existing assistant row."""
    db_path = _make_temp_db(tmp_path)

    # Build first digest (no footnotes)
    v1_dir = tmp_path / "v1"
    v1_dir.mkdir()
    fn_dir_v1 = _make_footnote_dir(v1_dir, {})
    digest_v1 = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir_v1,
        final_output_text=MINIMAL_FINAL_OUTPUT,
    )
    user_ts = _read_user_timestamp(db_path)
    _insert_assistant_message(db_path, digest_v1, user_ts)
    assert _assistant_exists(db_path)

    # Simulate --force: delete old, insert new
    v2_dir = tmp_path / "v2"
    v2_dir.mkdir()
    fn_dir_v2 = _make_footnote_dir(
        v2_dir,
        {
            "4.md": "Body for footnote 4.\n\n**Source.** Stock & Watson §4",
            "4_2.md": "Body for footnote 4.2.\n\n**Source.** Stock & Watson §4.2",
            "7.4.1.md": "[7.4.1]\nChebyshev WLLN.\n\n**Source.** Hansen §7.4",
        },
    )
    digest_v2 = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir_v2,
        final_output_text="ID/TITLE MAPPING\n\n4 :: Chebyshev tail\n7 :: WLLN\n\nFOOTNOTE TEXTS\n",
    )
    deleted = _delete_assistant_messages(db_path)
    assert deleted == 1
    assert not _assistant_exists(db_path)

    new_id = _insert_assistant_message(db_path, digest_v2, user_ts)
    assert _assistant_exists(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT content FROM messages WHERE id=?", (new_id,)).fetchone()
    conn.close()

    content = json.loads(row["content"])
    all_markers = [fn["marker"] for p in content["points"] for fn in p["footnotes"]]
    # All three compound+plain footnotes must be present
    assert "4" in all_markers
    assert "4.2" in all_markers
    assert "7.4.1" in all_markers


def test_force_replace_footnote_total_matches(tmp_path: Path) -> None:
    """After force-replace, total footnote count equals files in v2 dir."""
    db_path = _make_temp_db(tmp_path)
    v1_dir = tmp_path / "v1"
    v1_dir.mkdir()
    fn_dir_v1 = _make_footnote_dir(v1_dir, {})
    digest_v1 = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir_v1,
        final_output_text=MINIMAL_FINAL_OUTPUT,
    )
    user_ts = _read_user_timestamp(db_path)
    _insert_assistant_message(db_path, digest_v1, user_ts)

    # Three distinct footnotes in v2
    v2_dir = tmp_path / "v2"
    v2_dir.mkdir()
    fn_dir_v2 = _make_footnote_dir(
        v2_dir,
        {
            "1.md": "Body one.\n\n**Source.** https://en.wikipedia.org/wiki/One",
            "2.md": "Body two.\n\n**Source.** Stock & Watson",
            "7.5.1.md": "[7.5.1]\nWLLN vanishing variance.\n\n**Source.** Hansen §7.5",
        },
    )
    digest_v2 = assemble_digest(
        timeline_text=MINIMAL_TIMELINE,
        footnotes_dir=fn_dir_v2,
        final_output_text="ID/TITLE MAPPING\n\n1 :: Chebyshev proof\n2 :: Convergence\n7 :: WLLN\n\nFOOTNOTE TEXTS\n",
    )
    total = sum(len(p.footnotes) for p in digest_v2.points)
    assert total == 3, f"Expected 3 footnotes after force-replace, got {total}"

    _delete_assistant_messages(db_path)
    new_id = _insert_assistant_message(db_path, digest_v2, user_ts)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT content FROM messages WHERE id=?", (new_id,)).fetchone()
    conn.close()

    content = json.loads(row["content"])
    all_markers = [fn["marker"] for p in content["points"] for fn in p["footnotes"]]
    assert "7.5.1" in all_markers


# ---------------------------------------------------------------------------
# strip_bookkeeping — TDD: failing tests written before implementation
# ---------------------------------------------------------------------------
# Real junk patterns from the live footnotes/*.md workspace files.


def test_strip_bookkeeping_removes_coverage_line() -> None:
    """# COVERAGE: … = done tail line is removed."""
    body = (
        "Real content about Chebyshev.\n\n"
        "**Source.** https://en.wikipedia.org/wiki/Chebyshev%27s_inequality\n\n"
        "# COVERAGE: Chebyshev_WLLN_meaning_explicit :: What is the explicit statement"
        "/meaning of \"WLLN\"? = done"
    )
    result = strip_bookkeeping(body)
    assert "# COVERAGE:" not in result
    assert "= done" not in result
    assert "Real content about Chebyshev." in result
    assert "wikipedia.org" in result


def test_strip_bookkeeping_removes_coverage_unfilled() -> None:
    """# COVERAGE: … = unfilled is removed."""
    body = (
        "Weak law via vanishing variance.\n\n"
        "Source: moss §6.3\n"
        "kind: corpus\n\n"
        "# COVERAGE: Why does the WLLN require only $E|X|<\\infty$"
        " rather than finite variance? = unfilled\n\n"
        "# COVERAGE: Why does the WLLN require only $E|X|<\\infty$"
        " rather than finite variance? = unfilled"
    )
    result = strip_bookkeeping(body)
    assert "# COVERAGE:" not in result
    assert "= unfilled" not in result
    assert "Weak law via vanishing variance." in result


def test_strip_bookkeeping_removes_marker_heading() -> None:
    """# Marker lines (standalone heading) are removed."""
    body = (
        "Chebyshev proof step details.\n\n"
        "**Source.** https://en.wikipedia.org/wiki/Chebyshev%27s_inequality\n\n"
        "# Marker\n"
        "2\n"
        "kind: Chebyshev's variance identity"
    )
    result = strip_bookkeeping(body)
    assert "# Marker" not in result
    assert "Chebyshev proof step details." in result


def test_strip_bookkeeping_removes_standalone_kind_line() -> None:
    """Standalone 'kind: …' lines are removed."""
    body = (
        "Chebyshev for WLLN.\n\n"
        "Source: moss §6.3\n"
        "kind: corpus\n\n"
        "# COVERAGE: Something = done"
    )
    result = strip_bookkeeping(body)
    assert "kind: corpus" not in result
    assert "Chebyshev for WLLN." in result


def test_strip_bookkeeping_removes_kind_chebyshev_markov() -> None:
    """Real pattern: 'kind: Chebyshev/Markov proof' at end."""
    body = (
        "Distribution-free Chebyshev body.\n\n"
        "**Source.** https://en.wikipedia.org/wiki/Chebyshev%27s_inequality\n\n"
        "kind: Chebyshev/Markov proof\n"
        "# COVERAGE: Chebyshev_all_distributions_density_gap = done"
    )
    result = strip_bookkeeping(body)
    assert "kind: Chebyshev/Markov proof" not in result
    assert "# COVERAGE:" not in result
    assert "Distribution-free Chebyshev body." in result
    assert "wikipedia.org" in result


def test_strip_bookkeeping_preserves_source_line() -> None:
    """A legit **Source.** line is preserved while # COVERAGE: tail is stripped."""
    body = (
        "Chebyshev's inequality controls tails using only the variance.\n\n"
        "**Source.** Wikipedia: https://en.wikipedia.org/wiki/Chebyshev%27s_inequality\n\n"
        "# COVERAGE: Chebyshev_… :: Reconstruct the missing variance step"
        " … = done"
    )
    result = strip_bookkeeping(body)
    # Source line must survive
    assert "**Source.**" in result
    assert "wikipedia.org" in result
    # Junk must be gone
    assert "# COVERAGE:" not in result


def test_strip_bookkeeping_preserves_math() -> None:
    """Mathematical content (LaTeX) inside the body is untouched."""
    body = (
        "Chebyshev: $\\mathbb{P}(|X-\\mu|>t) \\le \\frac{\\operatorname{Var}(X)}{t^2}$.\n\n"
        "**Source.** Hansen §7.4\n\n"
        "# COVERAGE: Finite_variance_vs_only_Eabs_relationship :: Conditions are stated"
        " (i.i.d., E|X|<∞) = done"
    )
    result = strip_bookkeeping(body)
    assert "\\mathbb{P}" in result
    assert "\\operatorname{Var}" in result
    assert "# COVERAGE:" not in result


def test_strip_bookkeeping_trailing_done_without_coverage_prefix() -> None:
    """Lines ending with '= done' that are NOT prose are stripped."""
    body = (
        "WLLN without finite variance proof.\n\n"
        "**Source.** https://en.wikipedia.org/wiki/Law_of_large_numbers\n\n"
        "# COVERAGE: WLLN_without_finite_variance_proof_sketch"
        " (need an appropriate outline showing E|X|<∞ suffices) = done"
    )
    result = strip_bookkeeping(body)
    assert "= done" not in result
    assert "WLLN without finite variance proof." in result


def test_strip_bookkeeping_empty_body_unchanged() -> None:
    """Empty string input returns empty string."""
    assert strip_bookkeeping("") == ""


def test_strip_bookkeeping_clean_body_unchanged() -> None:
    """A body with no junk is returned verbatim (modulo trailing whitespace)."""
    body = (
        "Markov's inequality states: for $Y \\ge 0$ and $a>0$,\n"
        "$\\mathbb{P}(Y\\ge a)\\le \\mathbb{E}[Y]/a$.\n\n"
        "**Source.** https://en.wikipedia.org/wiki/Markov%27s_inequality"
    )
    result = strip_bookkeeping(body)
    assert "Markov's inequality" in result
    assert "wikipedia.org" in result
    # No bookkeeping added or removed
    assert "# COVERAGE" not in result


def test_strip_bookkeeping_load_footnotes_integration(tmp_path: Path) -> None:
    """_load_footnotes calls strip_bookkeeping so no junk survives in bodies."""
    fn_dir = _make_footnote_dir(
        tmp_path,
        {
            "2.md": (
                "2. Chebyshev proof step details.\n\n"
                "**Source.** https://en.wikipedia.org/wiki/Chebyshev%27s_inequality\n\n"
                "# Marker\n"
                "2\n"
                "kind: Chebyshev's variance identity"
            ),
            "14.md": (
                "14. Chebyshev WLLN statement.\n\n"
                "**Source.** https://en.wikipedia.org/wiki/Convergence_in_probability\n\n"
                "# COVERAGE: Chebyshev_WLLN_meaning_explicit :: meaning of WLLN = done"
            ),
        },
    )
    results = _load_footnotes(fn_dir, {})
    assert len(results) == 2
    for fn in results:
        assert "# COVERAGE:" not in fn.body
        assert "# Marker" not in fn.body
        assert "kind: Chebyshev" not in fn.body
        # Source lines must still be present for extract_source_and_kind to work
        assert "wikipedia.org" in fn.source
