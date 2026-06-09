"""Build the extension deepagents agent: orchestrator + analyst/polish/augmentor
subagents over a shared virtual filesystem.

Chinese-wall: imports deepagents + langgraph + sibling extension_agents only.
No deep_tutor, qa, or ow_* imports."""
from __future__ import annotations

import os

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.structured_output import ToolStrategy
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from src.core.config import settings
from src.services.chat.schemas import ExtensionDigest
from src.services.chat.agents.extension_agents._models import (
    STAGE_DEFAULTS,  # noqa: F401 — re-exported for test convenience
    resolve_stage_model,
    resolve_stage_temperature,
)
from src.services.chat.agents.extension_agents.prompts import (
    ANALYST_PROMPT,
    AUGMENTOR_PROMPT,
    ORCHESTRATOR_PROMPT,
    POLISH_PROMPT,
)
from src.services.chat.agents.extension_agents.tools import (
    make_retrieve_corpus,
    make_retrieve_peek,
    wikipedia_lookup,
)

# Absolute path to the extension_skills directory (sibling of extension_agents/).
SKILLS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "extension_skills")
)

# Repo root — the directory containing src/.  Used as FilesystemBackend root_dir
# so SKILL.md files resolve from the project tree in virtual_mode.
# Path depth from agent.py:
#   extension_agents/ -> agents/ -> chat/ -> services/ -> src/ -> <repo_root>
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)
assert os.path.isdir(os.path.join(_REPO_ROOT, "src")), (
    f"_REPO_ROOT={_REPO_ROOT!r} does not contain 'src/'; check __file__ depth"
)

# deepagents resolves `skills` paths through the FilesystemBackend, i.e.
# RELATIVE to root_dir (the documented form is ["./skills/"]). Absolute paths
# are not found in virtual_mode, so express the skills dir relative to the root.
SKILLS_REL = os.path.relpath(SKILLS_DIR, _REPO_ROOT)


def _lc_model(stage: str, stage_models: dict | None) -> ChatOpenAI:
    """Build a ChatOpenAI for a stage with explicit api_key and per-stage temperature."""
    return ChatOpenAI(
        model=resolve_stage_model(stage, stage_models),
        temperature=resolve_stage_temperature(stage),
        api_key=settings.openai_api_key,
        max_retries=6,
    )


def build_extension_agent(
    *,
    stage_models: dict | None,
    exclude_book: str,
    all_slugs: list[str],
    seen_ids: set[str] | None = None,
):
    """Create the deep-agent.

    Subagents carry their own stage models and tools.  The shared virtual
    filesystem (FilesystemBackend virtual_mode=True) persists across runner
    rounds when invoked with the same thread_id under the MemorySaver
    checkpointer.

    Args:
        stage_models: Optional per-stage model-id overrides (keys: orchestrator,
            analyst, polish, augmentor, judge).  None → all stage defaults.
        exclude_book: Slug of the book being extended — excluded from corpus
            retrieval so the agent draws only from peer books.
        all_slugs: Complete list of available book slugs (used for peek/corpus).
        seen_ids: Mutable set of chunk_ids already retrieved — deduped in
            retrieve_corpus to prevent duplicate footnotes across rounds.
    """
    peek = make_retrieve_peek(all_slugs=all_slugs)
    corpus = make_retrieve_corpus(
        exclude_book=exclude_book,
        all_slugs=all_slugs,
        seen_ids=seen_ids,
    )

    subagents = [
        {
            "name": "analyst",
            "description": (
                "Inspect one chapter section; report concept, key ideas, and gaps."
            ),
            "system_prompt": ANALYST_PROMPT,
            "model": _lc_model("analyst", stage_models),
            "tools": [peek],
            "skills": [os.path.join(SKILLS_REL, "curate-structure")],
        },
        {
            "name": "polish",
            "description": (
                "Curate per-section analyses into an ordered timeline of points."
            ),
            "system_prompt": POLISH_PROMPT,
            "model": _lc_model("polish", stage_models),
            "tools": [],
            "skills": [os.path.join(SKILLS_REL, "curate-structure")],
        },
        {
            "name": "augmentor",
            "description": (
                "Fill gap queries from other books + Wikipedia as footnotes only."
            ),
            "system_prompt": AUGMENTOR_PROMPT,
            "model": _lc_model("augmentor", stage_models),
            "tools": [corpus, wikipedia_lookup],
            "skills": [os.path.join(SKILLS_REL, "gap-augment")],
        },
    ]

    return create_deep_agent(
        name="extension",
        model=_lc_model("orchestrator", stage_models),
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=subagents,
        # Whole skills dir + the orchestrator/judge-specific skill explicitly.
        skills=[SKILLS_REL, os.path.join(SKILLS_REL, "judge-coverage")],
        backend=FilesystemBackend(root_dir=_REPO_ROOT, virtual_mode=True),
        checkpointer=MemorySaver(),
        # Enforce the final output shape so the orchestrator returns a parsed
        # ExtensionDigest (in result["structured_response"]) instead of loose
        # prose that the runner has to JSON-parse and may fail on.
        response_format=ToolStrategy(ExtensionDigest, handle_errors=True),
    )
