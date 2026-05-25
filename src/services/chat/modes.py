"""Mode registry for the chat service.

Defines ``ModeSpec``, ``RetrievalFlags``, and ``ModeRegistry``.  All 11 modes
are registered at import time via ``register_all_modes()`` (idempotent).

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``
modules. Never imports from ``src.ingestion`` or other services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Type

from pydantic import BaseModel

from src.services.chat.schemas import ModeId
from src.services.chat.schemas.output import (
    AnnotatedReading,
    CompareAnswer,
    DAG,
    FiguresAnswer,
    MathAnswer,
    NavigationList,
    Report,
    Roadmap,
    StudyPlan,
    TutorAnswer,
    Quiz,
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
    """Register all 11 mode specs.  Idempotent: no-op if already registered.

    Importing this module calls this function automatically, so callers only
    need to import ``modes`` to ensure the registry is populated.
    """
    if ModeRegistry._registry:
        return

    from src.services.chat.prompts import (  # noqa: PLC0415
        annotate as annotate_p,
        compare as compare_p,
        figures as figures_p,
        math as math_p,
        navigate as navigate_p,
        path as path_p,
        prereqs as prereqs_p,
        quiz as quiz_p,
        research as research_p,
        roadmap as roadmap_p,
        tutor as tutor_p,
    )

    # ------------------------------------------------------------------
    # 1. tutor — keep existing single-agent behaviour; rerank gated (M4)
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
    # 2. compare — per-book sections + synthesis
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="compare",
            icon="columns",
            arch="single",
            system_prompt=compare_p.INSTRUCTIONS,
            output_schema=CompareAnswer,
            tools=["retrieve_per_book"],
            retrieval_flags=RetrievalFlags(multi_query=2, rerank=True),
            model="pro",
            post_validators=("citation",),
            memory="sliding",
        )
    )

    # ------------------------------------------------------------------
    # 3. figures — figure-centred answer with vision gate
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="figures",
            icon="image",
            arch="single",
            system_prompt=figures_p.INSTRUCTIONS,
            output_schema=FiguresAnswer,
            tools=["retrieve", "retrieve_figures", "inspect_figure"],
            retrieval_flags=RetrievalFlags(adjacent_sections=True, rerank=True),
            model="pro_vision",
            post_validators=("citation", "vision_gate"),
            memory="sliding",
        )
    )

    # ------------------------------------------------------------------
    # 4. quiz — multiple-choice questions from retrieved sections
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="quiz",
            icon="check-square",
            arch="single",
            system_prompt=quiz_p.INSTRUCTIONS,
            output_schema=Quiz,
            tools=["retrieve"],
            retrieval_flags=RetrievalFlags(adjacent_sections=True, rerank=True),
            model="nano",
            post_validators=("citation", "self_check"),
            memory="off",
        )
    )

    # ------------------------------------------------------------------
    # 5. navigate — pure location list, no prose
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="navigate",
            icon="map-pin",
            arch="single",
            system_prompt=navigate_p.INSTRUCTIONS,
            output_schema=NavigationList,
            tools=["retrieve"],
            retrieval_flags=RetrievalFlags(hyde=True, rerank=True),
            model="nano",
            post_validators=("citation",),
            memory="off",
        )
    )

    # ------------------------------------------------------------------
    # 6. prereqs — concept DAG (multi-agent)
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="prereqs",
            icon="git-branch",
            arch="multi",
            system_prompt=prereqs_p.INSTRUCTIONS,
            output_schema=DAG,
            tools=[],
            retrieval_flags=RetrievalFlags(decompose=True, rerank=True),
            model="pro",
            max_graph_iters=12,
            post_validators=("citation", "cycle_check"),
            memory="off",
        )
    )

    # ------------------------------------------------------------------
    # 7. annotate — term annotation with definitions
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="annotate",
            icon="tag",
            arch="single",
            system_prompt=annotate_p.INSTRUCTIONS,
            output_schema=AnnotatedReading,
            tools=["extract_terms", "retrieve"],
            retrieval_flags=RetrievalFlags(multi_query=2, rerank=True),
            model="nano",
            post_validators=("citation",),
            memory="off",
        )
    )

    # ------------------------------------------------------------------
    # 8. research — claim extraction + stance classification (multi-agent)
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="research",
            icon="search",
            arch="multi",
            system_prompt=research_p.INSTRUCTIONS,
            output_schema=Report,
            tools=[],
            retrieval_flags=RetrievalFlags(decompose=True, rerank=True),
            model="pro",
            max_graph_iters=12,
            post_validators=("citation", "stance_consistency"),
            memory="off",
        )
    )

    # ------------------------------------------------------------------
    # 9. math — LaTeX-heavy answer with vision gate
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="math",
            icon="function",
            arch="single",
            system_prompt=math_p.INSTRUCTIONS,
            output_schema=MathAnswer,
            tools=["retrieve", "retrieve_figures", "inspect_figure"],
            retrieval_flags=RetrievalFlags(adjacent_sections=True, rerank=True),
            model="pro_vision",
            post_validators=("citation", "latex_check", "vision_gate"),
            memory="sliding",
        )
    )

    # ------------------------------------------------------------------
    # 10. path — multi-week study plan (multi-agent, persisted)
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="path",
            icon="route",
            arch="multi",
            system_prompt=path_p.INSTRUCTIONS,
            output_schema=StudyPlan,
            tools=[],
            retrieval_flags=RetrievalFlags(decompose=True, rerank=True),
            model="pro",
            max_graph_iters=15,
            post_validators=("citation", "coverage_check"),
            memory="persist",
        )
    )

    # ------------------------------------------------------------------
    # 11. roadmap — video production brief
    # ------------------------------------------------------------------
    ModeRegistry.register(
        ModeSpec(
            id="roadmap",
            icon="film",
            arch="single",
            system_prompt=roadmap_p.INSTRUCTIONS,
            output_schema=Roadmap,
            tools=["retrieve"],
            retrieval_flags=RetrievalFlags(
                multi_query=3, decompose=True, rerank=True
            ),
            model="pro",
            post_validators=("citation", "yaml_schema"),
            memory="off",
        )
    )


# Auto-register on import (idempotent)
register_all_modes()
