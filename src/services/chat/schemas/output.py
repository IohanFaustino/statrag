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
# Mode 2 — compare
# ---------------------------------------------------------------------------


class BookSection(BaseModel):
    """Per-book treatment of the queried concept."""

    book: str
    text: str
    citations: list[Citation]


class CompareAnswer(BaseModel):
    """Cross-book comparison with synthesis and divergence notes."""

    books: list[BookSection]
    synthesis: str
    divergences: list[str] = Field(default_factory=list)
    citations: list[Citation]


# ---------------------------------------------------------------------------
# Mode 3 — figures
# ---------------------------------------------------------------------------


class FiguresAnswer(BaseModel):
    """Answer centred on retrieved figures with supporting text."""

    figures: list[FigureRef]
    text: str
    citations: list[Citation]


# ---------------------------------------------------------------------------
# Mode 4 — quiz
# ---------------------------------------------------------------------------


class Question(BaseModel):
    """Single quiz question with options, answer key, rubric, and citation."""

    stem: str
    options: list[str]
    answer_idx: int  # 0-based index into options
    rubric: str
    source: Citation
    difficulty: Literal["easy", "medium", "hard"]
    self_check_passed: bool = True


class Quiz(BaseModel):
    """Set of quiz questions generated from retrieved sections."""

    questions: list[Question]


# ---------------------------------------------------------------------------
# Mode 5 — navigate
# ---------------------------------------------------------------------------


class NavResult(BaseModel):
    """Single navigation result pointing to a textbook location."""

    book: str
    chapter: str
    section: str
    title: str
    score: float
    page: int | None = None
    snippet: str = ""


class NavigationList(BaseModel):
    """Ordered list of matching locations with optional expansion terms."""

    results: list[NavResult]
    expanded_terms: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Mode 6 — prereqs
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


class DAG(BaseModel):
    """Prerequisite concept DAG with topological order and cycle-break log."""

    target: str = ""  # the queried concept
    nodes: list[ConceptNode]
    edges: list[ConceptEdge]
    order: list[str] = Field(default_factory=list)  # topo-sorted node ids
    cycles_broken: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Mode 7 — annotate
# ---------------------------------------------------------------------------


class Annotation(BaseModel):
    """Term annotation with definition, citation, and text position."""

    term: str
    definition: str
    source: Citation | None = None
    # T06: tuple[int, int] does not serialise cleanly via JSON Schema; switch
    # to a fixed-length list of two ints. Semantics unchanged: [start, end]
    # character offsets into the user input.
    position: list[int] = Field(default_factory=lambda: [0, 0], min_length=2, max_length=2)
    in_corpus: bool = True


class AnnotatedReading(BaseModel):
    """Annotated reading with per-term definitions and corpus gaps."""

    annotations: list[Annotation]
    not_in_corpus: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Mode 8 — research
# ---------------------------------------------------------------------------


class StanceClaim(BaseModel):
    """A single claim extracted from the research query with stance classification."""

    claim: str
    stance: Literal["SUPPORTS", "CONTRADICTS", "BACKGROUND"]
    evidence: list[Citation]
    confidence: float


class Report(BaseModel):
    """Research report with per-claim stance analysis and synthesis."""

    claims: list[StanceClaim]
    synthesis: str
    coverage_gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Mode 9 — math
# ---------------------------------------------------------------------------


class MathAnswer(BaseModel):
    """Math-focused answer with LaTeX blocks, figures, and citations."""

    latex_blocks: list[str]
    text: str
    figures: list[FigureRef] = Field(default_factory=list)
    citations: list[Citation]
    latex_check_passed: bool = True


# ---------------------------------------------------------------------------
# Mode 10 — path
# ---------------------------------------------------------------------------


class StudyWeek(BaseModel):
    """One week's study allocation: sections to read + time estimate."""

    week: int
    sections: list[Citation]
    goals: list[str] = Field(default_factory=list)
    hours_est: float = 2.0


class StudyPlan(BaseModel):
    """Multi-week personalised study plan with coverage gap analysis."""

    goal: str
    weeks: list[StudyWeek]
    total_weeks: int = 0
    coverage_gaps: list[str] = Field(default_factory=list)
    replanned_from_version: int = 0


# ---------------------------------------------------------------------------
# Mode 11 — roadmap
# ---------------------------------------------------------------------------


class Scene(BaseModel):
    """A single scene/segment in the video roadmap."""

    id: int
    title: str
    concept: str
    source: Citation
    suggested_visual: str
    duration_hint: str
    figure: str | None = None


class Roadmap(BaseModel):
    """Video production brief: ordered scenes covering a statistical topic."""

    topic: str
    target_audience: str = ""
    total_duration_estimate: str = ""
    duration_total_min: int = 0
    scenes: list[Scene]
