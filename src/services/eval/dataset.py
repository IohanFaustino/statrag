"""JSONL-backed dataset of Q/A records for the evaluation harness.

Wall rule: no imports from src.services.chat or src.ingestion.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class QARecord(BaseModel):
    id: str                        # stable identifier
    q: str                         # question text
    gold_book: str                 # expected book slug
    gold_chapter: str              # expected chapter_id (e.g. "ch06")
    gold_section: str              # h2_path or last-segment label
    gold_chunk_id: str | None = None
    gold_answer: str               # reference answer (a few sentences)
    tags: list[str] = []           # mode-relevance tags: ["tutor","compare", ...]


def load(path: Path) -> list[QARecord]:
    """Load Q/A records from a JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of validated QARecord instances.
    """
    out: list[QARecord] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(QARecord.model_validate_json(line))
    return out


def save(path: Path, records: list[QARecord]) -> None:
    """Persist Q/A records to a JSONL file.

    Args:
        path: Destination path. Parent directories are created automatically.
        records: Records to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write(r.model_dump_json() + "\n")
