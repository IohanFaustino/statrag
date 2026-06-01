"""Per-mode structured output schemas.

Every mode's LLM response is validated against one of these Pydantic models.
On ValidationError the orchestrator runs one schema-repair retry (ADR-005).

Chinese-wall: imports only stdlib + pydantic. No src.* imports.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    """Traceable reference to a textbook section."""

    book: str  # slug, e.g. "islp"
    chapter: str  # e.g. "ch02"
    section: str  # e.g. "2.2.1"
    page: int | None = None
    chunk_id: str = ""  # for traceability + highlight


ASPECT_HINT = Literal[
    "tldr",
    "definition",
    "formal_statement",
    "example_intuition",
    "applications",
    "further_reading",
]


class FigureRef(BaseModel):
    """Reference to a figure retrieved from the image collection."""

    ref: str
    book: str
    chapter: str
    caption: str = ""
    url: str = ""
    vision_used: bool = False
    vision_answer: str | None = None
    # Deep-tutor image pipeline annotations (default-safe for older callers).
    aspect_hint: ASPECT_HINT | None = None
    figure_role: Literal["diagram", "graph", "chart", "table", "equation", "photo", "other"] | None = None
    judge_confidence: float | None = None
    judge_reason: str = ""


# ---------------------------------------------------------------------------
# Mode 1 — tutor
# ---------------------------------------------------------------------------


class TutorCitation(BaseModel):
    """T13-E: machine-readable per-claim citation span for tutor mode.

    The frontend renders the ``index`` field as a clickable `[¹]` badge that
    opens a card showing ``quote``, ``authors_short``, ``year``, page range,
    and a link back to the source chunk.
    """

    index: int                       # 1-based [¹] number used inline
    chunkId: str = ""
    authors_short: str = ""
    year: int | None = None
    book_name: str = ""
    chapter: str = ""
    section: str = ""
    page_from: int | None = None
    page_to: int | None = None
    quote: str = ""                  # the exact sentence the cite supports


class TutorAnswer(BaseModel):
    """Tutor mode answer with structured per-claim citation spans.

    T13-E rewrite: ``text`` is markdown with inline ``[1]`` markers that
    line up 1:1 with the ``citations`` array (matched on ``index``).
    ``sections`` lists the H2 headings the LLM chose so the UI can render
    a table of contents.

    ``aspects`` (deep-tutor) carries the explicit per-aspect strings
    (``tldr``, ``definition``, ``formal_statement``, ``example_intuition``,
    ``applications``, ``further_reading``).  Older frontends
    ignore the field; deep-tutor-aware UIs can render it as cards /
    accordion.  ``text`` is always the assembled markdown so legacy
    renderers keep working.
    """

    text: str
    sections: list[str] = Field(default_factory=list)
    citations: list[TutorCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)
    figures: list[FigureRef] = Field(default_factory=list)
    aspects: dict[str, str] = Field(default_factory=dict)
    # Audit signals (deep-tutor). e.g. ``example_relevance`` in [0,1]:
    # lexical overlap of the ``example_intuition`` aspect with the concept it
    # should illustrate (definition + formal_statement). Older
    # frontends ignore the field.
    quality: dict[str, float] = Field(default_factory=dict)


class DeepTutorAnswer(BaseModel):
    """Strongly-typed multi-aspect tutor answer.

    Used as the LLM ``response_format`` for the deep-tutor draft pass.
    Each field is required so the model must produce substantive content
    per aspect (typically 100-200 words each).  The orchestrator converts
    a ``DeepTutorAnswer`` to a back-compatible :class:`TutorAnswer` by
    assembling ``text`` from the aspect fields and packing the raw
    aspect strings into ``aspects``.
    """

    tldr: str = Field(
        ...,
        description=(
            "Introduction: 2-3 sentence direct answer, then a one-sentence "
            "roadmap of the sections that follow."
        ),
    )
    definition: str = Field(..., description="Markdown paragraph defining the concept.")
    formal_statement: str = Field(
        ...,
        description=(
            "Verbatim numbered theorem/definition when the sources state one "
            "('Conforming to Definition X.Y.Z, …' + blockquote); otherwise an "
            "EMPTY STRING (the heading is dropped when empty)."
        ),
    )
    example_intuition: str = Field(
        ...,
        description=(
            "Example & Intuition merged: describe three cases, analyse the "
            "three, then state explicitly 'the intuition here is that …'."
        ),
    )
    applications: str = Field(
        ...,
        description="Corpus-grounded use-cases grouped by domain (marketing, finance, …).",
    )
    further_reading: str = Field(
        ...,
        description=(
            "Pointer to related topics with citations, plus a short list "
            "of 2-3 open/related research questions extending this topic."
        ),
    )
    citations: list[TutorCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)
    figures: list[FigureRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Deep-tutor synthesis plan (workflow A — evidence ledger + plan)
# ---------------------------------------------------------------------------


class AuthorContrast(BaseModel):
    """A point where two sources frame the concept differently — surfaced so
    the draft can compare them explicitly rather than blend them."""

    topic: str
    author_a: str = ""
    position_a: str = ""
    author_b: str = ""
    position_b: str = ""


class WorkerTask(BaseModel):
    """One subtask the orchestrator LLM decides to delegate to a worker.

    ``focus`` is what the worker should cover (e.g. an author's treatment, or a
    sub-topic); ``source_ranks`` are the ``[#rank]`` sources to hand it."""

    focus: str = ""
    source_ranks: list[int] = Field(default_factory=list)


class OrchestratorPlan(BaseModel):
    """Output of the orchestrator step: the dynamically-chosen subtasks."""

    tasks: list[WorkerTask] = Field(default_factory=list)


class AuthorBrief(BaseModel):
    """Output of one orchestrator worker: how a single author treats the
    queried concept, grounded only in that author's sources."""

    author: str = ""
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    source_ranks: list[int] = Field(default_factory=list)


class SynthesisPlan(BaseModel):
    """The Planner's output: a single throughline, explicit author contrasts,
    and the worker decomposition. Planner + Orchestrator are one agent.

    Kept lean ({thesis, contrasts, tasks}) so it fits the token budget and is
    valid for OpenAI strict structured outputs (no open-keyed dicts)."""

    thesis: str = ""
    contrasts: list[AuthorContrast] = Field(default_factory=list)
    # Worker decomposition for the orchestrator drafting workflow.
    tasks: list[WorkerTask] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Mode 2 — qa (punctual Q&A)
# ---------------------------------------------------------------------------


class QAScope(BaseModel):
    """Parsed scope of a punctual question.

    ``target_gap`` is the precise thing to answer; ``assumed_known`` lists what
    the user already understands (so generation must NOT re-explain it);
    ``answer_form`` hints the shape of the reply.
    """

    target_gap: str
    assumed_known: list[str] = Field(default_factory=list)
    answer_form: Literal[
        "explanation", "definition", "comparison",
        "derivation", "yes_no", "list",
    ] = "explanation"


class QAAnswer(BaseModel):
    """Lean, punctual Q&A answer.

    Deliberately smaller than :class:`TutorAnswer`: no sections, figures, or
    aspects. ``text`` is terse markdown with inline ``[n]`` citation markers
    that line up with ``citations``. ``scope`` is echoed for UI transparency;
    ``grounding`` carries the verify-node verdict
    (``{ok: bool, unsupported: list[str], confidence: float}``).
    """

    text: str
    scope: QAScope
    citations: list[TutorCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Mode 3/4 — chapter (facilitate + resume)
# ---------------------------------------------------------------------------


class ResolvedSubtopic(BaseModel):
    """One requested subtopic mapped to a real chapter heading.

    ``matched_h2`` is "" when the request could not be resolved (dropped).
    ``score`` is the match confidence (1.0 for the whole-chapter default).
    """

    asked: str
    matched_h2: str = ""
    section_id: str = ""
    score: float = 0.0


class ChapterScope(BaseModel):
    """Resolved scope for a chapter-mode run.

    ``requested_subtopics`` empty means "whole chapter, in order".
    ``resolution`` echoes the closest-match mapping for UI transparency.
    """

    book_slug: str
    chapter_id: str
    requested_subtopics: list[str] = Field(default_factory=list)
    resolution: list[ResolvedSubtopic] = Field(default_factory=list)


class ChapterBlock(BaseModel):
    """One subtopic's rendered block. List position in ``ChapterDigest.blocks``
    IS the chapter order — never re-sorted by the frontend."""

    h2_path: str
    section_id: str
    body: str
    page_from: int = -1
    page_to: int = -1


class ChapterDigest(BaseModel):
    """Ordered chapter digest shared by ``facilitate`` and ``resume``.

    ``mode`` tells the renderer which header/styling to use. ``blocks`` are in
    chapter order. Reuses :class:`TutorCitation` so existing citation cards
    render unchanged. ``grounding`` carries the verify-node verdict.
    """

    mode: Literal["facilitate", "resume"]
    scope: ChapterScope
    intro: str = ""
    blocks: list[ChapterBlock] = Field(default_factory=list)
    outro: str = ""
    citations: list[TutorCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scope resolver schemas (book catalog + resolution)
# ---------------------------------------------------------------------------


class CatalogBook(BaseModel):
    slug: str
    name: str
    authors_short: str = ""
    field: str = ""
    chapters: list[str] = Field(default_factory=list)  # ordered chNN ids


class BookResolution(BaseModel):
    book_slug: str = ""
    book_confidence: float = 0.0
    book_candidates: list[str] = Field(default_factory=list)
    chapter_id: str = ""
    requested_subtopics: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Concept graph primitives (kept — kg.py depends on these)
# ---------------------------------------------------------------------------


class ConceptNode(BaseModel):
    """A concept node in the prerequisite DAG."""

    id: str
    label: str
    source: Citation | None = None


class ConceptEdge(BaseModel):
    """Directed prerequisite edge between two concept nodes."""

    from_id: str
    to_id: str
    weight: float = 1.0


