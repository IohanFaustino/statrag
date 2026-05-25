"""Unit tests for the evaluation harness.

Covers dataset roundtrip and the two deterministic metrics (context_precision,
context_recall). No LLM calls are made.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from src.services.eval.dataset import QARecord, load, save
from src.services.eval.metrics import context_precision, context_recall


# ---------------------------------------------------------------------------
# Dataset tests
# ---------------------------------------------------------------------------


def test_dataset_roundtrip(tmp_path: Path) -> None:
    """Records serialised to JSONL and re-loaded must be identical."""
    recs = [
        QARecord(
            id="r1",
            q="x?",
            gold_book="islp",
            gold_chapter="ch06",
            gold_section="§6.2",
            gold_chunk_id="abc",
            gold_answer="a.",
        )
    ]
    p = tmp_path / "x.jsonl"
    save(p, recs)
    out = load(p)
    assert out == recs


def test_dataset_roundtrip_multiple_records(tmp_path: Path) -> None:
    """Multiple records with varying optional fields survive roundtrip."""
    recs = [
        QARecord(
            id=f"r{i}",
            q=f"question {i}?",
            gold_book="islp",
            gold_chapter=f"ch0{i}",
            gold_section=f"§{i}",
            gold_answer=f"Answer {i}.",
            tags=["tutor", "compare"],
        )
        for i in range(1, 4)
    ]
    p = tmp_path / "multi.jsonl"
    save(p, recs)
    out = load(p)
    assert out == recs


def test_dataset_empty_file(tmp_path: Path) -> None:
    """Loading an empty JSONL file returns an empty list."""
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    assert load(p) == []


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    """save() should create parent directories if they do not exist."""
    p = tmp_path / "nested" / "deep" / "records.jsonl"
    recs = [
        QARecord(
            id="r1",
            q="q?",
            gold_book="islp",
            gold_chapter="ch01",
            gold_section="§1",
            gold_answer="ans.",
        )
    ]
    save(p, recs)
    assert p.exists()
    assert load(p) == recs


# ---------------------------------------------------------------------------
# context_precision tests
# ---------------------------------------------------------------------------


def test_context_precision_hit() -> None:
    assert context_precision([{"chunkId": "abc"}], "abc") == 1.0


def test_context_precision_miss() -> None:
    assert context_precision([{"chunkId": "xyz"}], "abc") == 0.0


def test_context_precision_partial_hit() -> None:
    chunks = [{"chunkId": "abc"}, {"chunkId": "xyz"}, {"chunkId": "def"}]
    result = context_precision(chunks, "abc")
    assert abs(result - 1 / 3) < 1e-9


def test_context_precision_empty_chunks() -> None:
    """Empty retrieved set should return 0.0."""
    assert context_precision([], "abc") == 0.0


def test_context_precision_no_gold_returns_one() -> None:
    """When gold_chunk_id is None, return permissive 1.0."""
    assert context_precision([{"chunkId": "a"}], None) == 1.0


def test_context_precision_no_gold_empty_chunks() -> None:
    """Empty chunks with no gold should still return 0.0 (empty guard fires first)."""
    assert context_precision([], None) == 0.0


# ---------------------------------------------------------------------------
# context_recall tests
# ---------------------------------------------------------------------------


def test_context_recall_present() -> None:
    assert context_recall([{"chunkId": "abc"}, {"chunkId": "z"}], "abc") == 1.0


def test_context_recall_absent() -> None:
    assert context_recall([{"chunkId": "z"}], "abc") == 0.0


def test_context_recall_no_gold_returns_one() -> None:
    """When gold_chunk_id is None, recall is permissive 1.0."""
    assert context_recall([{"chunkId": "z"}], None) == 1.0


def test_context_recall_empty_chunks_with_gold() -> None:
    """Empty retrieved set with a gold id should return 0.0 (gold not found)."""
    assert context_recall([], "abc") == 0.0
