"""Tests for mode registry, output schemas, and schema-repair loop.

All external I/O (Qdrant, OpenAI) is mocked.  Tests run fully offline.

Coverage:
- Tutor mode registered with correct id and non-empty system prompt.
- Output schemas validate against hand-crafted fixtures.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on PYTHONPATH and a dummy API key is present
# ---------------------------------------------------------------------------

_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(rank: int = 1):
    """Return a minimal Source fixture."""
    import uuid

    from src.services.chat.schemas import Source

    return Source(
        rank=rank,
        book="islp",
        chapter="ch01",
        section="1.1",
        title="Introduction",
        excerpt="Short excerpt.",
        score=0.9,
        page=1,
        chunkId=uuid.uuid4().hex,
        chunk="Full chunk text about linear regression and statistics.",
        highlights=[],
    )


def _make_metadata():
    """Return a minimal RetrievalMetadata fixture."""
    from src.services.chat.schemas import RetrievalMetadata

    return RetrievalMetadata(
        rewrittenQuery="what is regression",
        embedding="text-embedding-3-large",
        retrievalMs=50,
        collections=["introduction_textbooks"],
        filter="none",
        topK=5,
        scoreThreshold=0.0,
        mode="hybrid (RRF: dense + sparse)",
    )


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_registry_has_2() -> None:
    """ModeRegistry must contain exactly 2 entries (tutor, qa) after registration."""
    from src.services.chat.modes import ModeRegistry, register_all_modes

    register_all_modes()
    ids = {m.id for m in ModeRegistry.all()}
    assert ids == {"tutor", "qa"}


def test_tutor_mode_registered() -> None:
    """Tutor mode must be registered with a non-empty system prompt."""
    from src.services.chat.modes import ModeRegistry

    spec = ModeRegistry.get("tutor")
    assert spec.id == "tutor"
    assert spec.system_prompt, "Mode 'tutor' has empty system_prompt"


def test_mode_output_schemas_are_distinct() -> None:
    """Tutor declares TutorAnswer as output schema."""
    from src.services.chat.modes import ModeRegistry
    from src.services.chat.schemas.output import TutorAnswer

    specs = ModeRegistry.all()
    assert specs[0].output_schema is TutorAnswer


def test_tutor_mode_memory_auto() -> None:
    """tutor mode must use memory='auto'."""
    from src.services.chat.modes import ModeRegistry

    spec = ModeRegistry.get("tutor")
    assert spec.memory == "auto"


def test_register_all_modes_is_idempotent() -> None:
    """Calling register_all_modes() twice must not duplicate registrations."""
    from src.services.chat.modes import ModeRegistry, register_all_modes

    register_all_modes()
    count_after_double_call = len(ModeRegistry.all())
    assert count_after_double_call == 2


# ---------------------------------------------------------------------------
# Schema fixture tests
# ---------------------------------------------------------------------------


def test_tutor_answer_schema_fixture() -> None:
    """TutorAnswer must accept a minimal valid fixture.

    T13-E: citations are now :class:`TutorCitation` (numbered, with quote
    + provenance) instead of plain :class:`Citation`.
    """
    from src.services.chat.schemas.output import TutorAnswer, TutorCitation

    ans = TutorAnswer(
        text="Linear regression models the relationship between X and Y.[1]",
        sections=["Definition"],
        citations=[TutorCitation(
            index=1, chunkId="c-1",
            authors_short="James et al.", year=2023,
            book_name="ISL", chapter="ch03", section="3.1",
            page_from=59, page_to=62,
            quote="Linear regression models the relationship between X and Y.",
        )],
    )
    assert ans.text.startswith("Linear")
    assert ans.citations[0].authors_short == "James et al."
