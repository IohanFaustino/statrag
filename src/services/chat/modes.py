"""Mode registry for the chat service.

Defines ``ModeSpec``, ``RetrievalFlags``, and ``ModeRegistry``.  The tutor mode
is registered at import time via ``register_all_modes()`` (idempotent).

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``
modules. Never imports from ``src.ingestion`` or other services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Type

from pydantic import BaseModel

from src.services.chat.schemas import ModeId
from src.services.chat.schemas.output import (
    TutorAnswer,
)


# ---------------------------------------------------------------------------
# RetrievalFlags
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalFlags:
    """Flags that control query-expansion and retrieval behaviour per mode.

    Attributes:
        hyde: Generate a hypothetical passage and use it for dense retrieval.
        multi_query: Number of query paraphrases (0 = off).
        decompose: Decompose complex queries into atomic sub-queries.
        adjacent_sections: Expand each surviving chunk to adjacent sections.
        rerank: Run cross-encoder reranker after RRF fusion.
        rerank_top_n: Maximum results to keep after reranking.
    """

    hyde: bool = False
    multi_query: int = 0
    decompose: bool = False
    adjacent_sections: bool = False
    rerank: bool = True
    rerank_top_n: int = 8


# ---------------------------------------------------------------------------
# ModeSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModeSpec:
    """Specification for one chat mode.

    Attributes:
        id: Canonical mode identifier (matches ``ModeId`` Literal).
        icon: Short icon slug for the UI (e.g. ``"book"``).
        arch: ``"single"`` for tool-loop; ``"multi"`` for state-graph runner.
        system_prompt: Full system message (persona + hard rules).
        few_shot: Optional few-shot examples (list of dicts).
        output_schema: Pydantic model class to validate LLM output against.
        tools: Tool names available in single-agent tool-loop.
        retrieval_flags: Query-expansion and retrieval settings.
        model: Model tier — ``"nano"``, ``"pro"``, or ``"pro_vision"``.
        max_tool_calls: Maximum tool invocations per turn (single-agent).
        max_graph_iters: Maximum node visits per run (multi-agent).
        post_validators: Names of post-process validators to apply.
        memory: Memory strategy for this mode.
    """

    id: ModeId
    icon: str
    arch: Literal["single", "multi"]
    system_prompt: str
    few_shot: list = field(default_factory=list)
    output_schema: Type[BaseModel] = TutorAnswer
    tools: list[str] = field(default_factory=list)
    retrieval_flags: RetrievalFlags = field(default_factory=RetrievalFlags)
    model: Literal["nano", "pro", "pro_vision"] = "nano"
    max_tool_calls: int = 3
    max_graph_iters: int = 12
    post_validators: tuple[str, ...] = ("citation",)
    memory: Literal["off", "sliding", "summary", "vec", "auto", "persist"] = "off"


# ---------------------------------------------------------------------------
# ModeRegistry
# ---------------------------------------------------------------------------


class ModeRegistry:
    """Singleton registry mapping mode IDs to ``ModeSpec`` instances."""

    _registry: dict[str, ModeSpec] = {}

    @classmethod
    def register(cls, spec: ModeSpec) -> None:
        """Register a ``ModeSpec``.  Overwrites if already present.

        Args:
            spec: The mode specification to register.
        """
        cls._registry[spec.id] = spec

    @classmethod
    def get(cls, mode_id: str) -> ModeSpec:
        """Return the ``ModeSpec`` for *mode_id*.

        Args:
            mode_id: Canonical mode identifier.

        Returns:
            The registered ``ModeSpec``.

        Raises:
            KeyError: If *mode_id* is not registered.
        """
        if mode_id not in cls._registry:
            raise KeyError(f"Unknown mode: {mode_id!r}")
        return cls._registry[mode_id]

    @classmethod
    def all(cls) -> list[ModeSpec]:
        """Return all registered ``ModeSpec`` instances.

        Returns:
            List of all registered specs (order not guaranteed).
        """
        return list(cls._registry.values())


# ---------------------------------------------------------------------------
# register_all_modes
# ---------------------------------------------------------------------------


def register_all_modes() -> None:
    """Register the tutor mode spec.  Idempotent: no-op if already registered.

    Importing this module calls this function automatically, so callers only
    need to import ``modes`` to ensure the registry is populated.
    """
    if ModeRegistry._registry:
        return

    from src.services.chat.prompts import tutor as tutor_p  # noqa: PLC0415

    # ------------------------------------------------------------------
    # tutor — keep existing single-agent behaviour; rerank gated (M4)
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="tutor",
            icon="book",
            arch="single",
            system_prompt=tutor_p.TUTOR_INSTRUCTIONS,
            output_schema=TutorAnswer,
            tools=["retrieve"],
            retrieval_flags=RetrievalFlags(rerank=False),  # rerank gated until M4
            model="nano",
            post_validators=("citation",),
            memory="auto",
        )
    )

    # ------------------------------------------------------------------
    # qa — punctual Q&A; multi-node graph (scope→retrieve→generate→verify)
    # ------------------------------------------------------------------
    from src.services.chat.prompts.qa import QA_GENERATE_PROMPT  # noqa: PLC0415
    from src.services.chat.schemas.output import QAAnswer  # noqa: PLC0415

    ModeRegistry.register(
        ModeSpec(
            id="qa",
            icon="target",
            arch="multi",
            system_prompt=QA_GENERATE_PROMPT,
            output_schema=QAAnswer,
            tools=[],
            retrieval_flags=RetrievalFlags(rerank=True, rerank_top_n=4),
            model="nano",
            post_validators=(),
            memory="off",
        )
    )


# Auto-register on import (idempotent)
register_all_modes()
