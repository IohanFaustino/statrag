"""Tool surface for v2 single-agent modes.

Each tool here is a :func:`langchain_core.tools.tool`-decorated function
ready to register on a :func:`langchain.agents.create_agent` call. Tools are
intentionally cheap: they wrap existing chat-service helpers and return
JSON-serialisable payloads so the agent's context window stays bounded.

ADR-009: tool surface is no longer decorative; the v2 modes register these
to give the LLM real function-calling capability over retrieval, figure
inspection, term extraction, and KG lookup.

Chinese-wall: imports only sibling chat modules.
"""
from src.services.chat.tools.extract_terms import extract_terms
from src.services.chat.tools.inspect_figure import inspect_figure, inspect_figure_tool
from src.services.chat.tools.kg_neighbors import kg_neighbors
from src.services.chat.tools.retrieve import retrieve
from src.services.chat.tools.retrieve_figures import retrieve_figures
from src.services.chat.tools.retrieve_per_book import retrieve_per_book

__all__ = [
    "retrieve",
    "retrieve_per_book",
    "retrieve_figures",
    "inspect_figure_tool",
    "inspect_figure",  # legacy direct-call shim for v1 orchestrator
    "extract_terms",
    "kg_neighbors",
]
