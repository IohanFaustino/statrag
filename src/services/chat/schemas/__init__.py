"""Schemas package for the chat service.

Re-exports every name from the original ``_core`` module (previously
``schemas.py``) so that all existing ``from src.services.chat.schemas import
...`` statements continue to work without change.

Also re-exports the per-mode output models from ``output.py``.

Chinese-wall: imports only stdlib and pydantic sub-modules. No src.core.* needed.
"""
from __future__ import annotations

from src.services.chat.schemas._core import (  # noqa: F401
    Book,
    ChatRequest,
    ConversationDigest,
    Figure,
    HighlightRange,
    Model,
    ModelProvider,
    ModeId,
    ProviderId,
    RetrievalMetadata,
    SearchRequest,
    Source,
)
from src.services.chat.schemas.output import (  # noqa: F401
    Citation,
    ConceptEdge,
    ConceptNode,
    FigureRef,
    TutorAnswer,
    TutorCitation,
    DeepTutorAnswer,
    AuthorContrast,
    WorkerTask,
    OrchestratorPlan,
    AuthorBrief,
    SynthesisPlan,
    QAScope,
    QAAnswer,
    ChapterScope,
    ChapterBlock,
    ChapterDigest,
    ResolvedSubtopic,
    CatalogBook,
    BookResolution,
    ConceptProvenance,
    ConceptAnchor,
    FacilitateBlock,
    FacilitateDigest,
    FacilitateMap,
    FacilitateVerify,
)

__all__ = [
    # _core
    "Book",
    "ChatRequest",
    "ConversationDigest",
    "Figure",
    "HighlightRange",
    "Model",
    "ModelProvider",
    "ModeId",
    "ProviderId",
    "RetrievalMetadata",
    "SearchRequest",
    "Source",
    # output
    "Citation",
    "ConceptEdge",
    "ConceptNode",
    "FigureRef",
    "TutorAnswer",
    "TutorCitation",
    "DeepTutorAnswer",
    "AuthorContrast",
    "WorkerTask",
    "OrchestratorPlan",
    "AuthorBrief",
    "SynthesisPlan",
    "QAScope",
    "QAAnswer",
    "ChapterScope",
    "ChapterBlock",
    "ChapterDigest",
    "ResolvedSubtopic",
    "CatalogBook",
    "BookResolution",
    "ConceptProvenance",
    "ConceptAnchor",
    "FacilitateBlock",
    "FacilitateDigest",
    "FacilitateMap",
    "FacilitateVerify",
]
