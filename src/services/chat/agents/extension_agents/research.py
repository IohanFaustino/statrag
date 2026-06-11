"""Extension v2 researcher — re-export shim.

All logic lives in src.services.chat.research (shared with Q&A).
This module re-exports every name that extension_agents internals and tests
import so that all existing import paths remain valid.
"""
from __future__ import annotations

# Re-export shared primitives — keeps existing imports working.
from src.services.chat.research import (  # noqa: F401
    Evidence,
    _WIKI_HEADERS,
    _WIKI_SEARCH,
    _WIKI_SUMMARY,
    _seen_lock,
    _wiki_summary_json,
    corpus_evidence,
    wiki_evidence,
)
