"""Pydantic schemas shared across routes + orchestrator.

Mirrors the TS types in `web/src/types.ts`. Keep both in sync.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ModeId = Literal["tutor", "qa", "facilitate", "resume"]
ProviderId = Literal["openai", "deepseek", "groq", "google", "alibaba"]


class Book(BaseModel):
    id: str                          # book slug, e.g. "islp"
    title: str
    subtitle: str = ""
    short: str
    authors: str
    authorsShort: str
    edition: str
    chunks: int
    figures: int
    chapters: int
    color: str
    cover: str
    description: str
    collection: str                  # text collection (per-field)
    image_collection: str            # image collection (per-field)
    field: str
    theme: str
    selected: bool = True
    indexed: bool = True


class HighlightRange(BaseModel):
    start: int
    end: int
    reason: str | None = None


class Source(BaseModel):
    rank: int
    book: str
    chapter: str
    section: str
    title: str
    excerpt: str
    score: float
    # T05: preserve pre-rerank RRF score so callers can distinguish retrieval
    # confidence from cross-encoder logits. Defaults to ``score`` when the
    # reranker has not yet run.
    raw_score: float | None = None
    page: int | None = None
    chunkId: str
    embedding: str = "text-embedding-3-large"
    chunk: str
    highlights: list[HighlightRange] = Field(default_factory=list)

    # T13-A: full provenance for APA-style citations. Defaults keep legacy
    # callers working — fields are populated by `_point_to_source` when the
    # corresponding Qdrant payload keys exist.
    book_name: str = ""
    authors: str = ""               # comma-joined full names from ingestion
    authors_short: str = ""         # "Smith et al." form
    year: int | None = None
    page_from: int | None = None
    page_to: int | None = None


class Figure(BaseModel):
    ref: str
    book: str
    chapter: str
    caption: str
    chart: str                       # URL or built-in kind


class RetrievalMetadata(BaseModel):
    rewrittenQuery: str
    embedding: str
    retrievalMs: int
    collections: list[str]
    filter: str
    topK: int
    scoreThreshold: float
    mode: str


class Model(BaseModel):
    id: str
    name: str
    tagline: str
    cost: str
    speed: str
    ctx: str
    recommended: bool = False


class ModelProvider(BaseModel):
    id: ProviderId
    name: str
    short: str
    color: str
    models: list[Model]


class ChatRequest(BaseModel):
    conversationId: str | None = None
    message: str
    mode: ModeId = "tutor"
    model: str = "gpt-5.4-nano-2026-03-17"
    bookFilter: list[str] | Literal["ALL"] = "ALL"
    attachments: list[dict[str, Any]] | None = None

    # Per-stage model overrides for the tutor pipeline (About-model feature).
    # Keys are pipeline stage ids (e.g. "expansion", "draft", "critique",
    # "image_judge"); values are model ids from the picker registry. Unknown
    # stages/models are ignored and fall back to the stage default. ``None``
    # (the common case) preserves the legacy single-``model`` behaviour.
    stageModels: dict[str, str] | None = None

    # T13-F: user-controllable inference + retrieval knobs. ``None`` defers to
    # the mode's default (set in the create_agent call / tool default).
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_k: int | None = Field(default=None, ge=1, le=20)
    rerank: bool | None = None

    # Author-perspective diversity (tutor retrieval). Caps the number of distinct
    # authors the section selection spans (author primary, year tiebreak).
    #   "auto" = the concept-extraction model picks the count (clamped to the env
    #            cap and to how many authors actually exist in the pool);
    #   0/1    = off;  N>=2 = hard cap;  None = env default (auto when enabled).
    # The effective count is always <= authors available, so a single-author
    # topic yields a single author regardless of this value.
    diversityAuthors: int | Literal["auto"] | None = None

    # Drafting workflow: ``"single"`` = one draft call writes all aspects (legacy);
    # ``"orchestrator"`` = one worker per author + a synthesizer integrate pass.
    # ``"orchestrator-deep"`` = orchestrator workers + the deepagents+SKILL deep
    #   synthesizer (Plan D, opt-in, ~45 s blocking; falls back to L0 on failure).
    # ``None`` defers to the ``TUTOR_WORKFLOW`` env default.
    tutorWorkflow: Literal["single", "orchestrator", "orchestrator-deep", "organize"] | None = None


class SearchRequest(BaseModel):
    query: str
    books: list[str] | None = None
    topK: int = 5
    scoreThreshold: float = 0.0


class ConversationDigest(BaseModel):
    id: str
    title: str
    mode: ModeId = "tutor"
    createdAt: str
    updatedAt: str
    bookFilter: list[str] | Literal["ALL"] = "ALL"
    modelId: str = "gpt-5.4-nano-2026-03-17"
