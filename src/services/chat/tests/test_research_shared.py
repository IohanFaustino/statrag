"""Tests for the shared research.py module (Evidence + wiki/corpus + _citation).

Verifies:
1. Public imports from src.services.chat.research resolve.
2. _citation produces a StoryCitation with fields from Evidence.meta for wikipedia kind.
3. Extension shims still expose the same names (backward-compat re-exports).
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 1. Direct imports from shared module
# ---------------------------------------------------------------------------

def test_shared_imports():
    from src.services.chat.research import (  # noqa: F401
        Evidence,
        corpus_evidence,
        wiki_evidence,
        _citation,
    )


# ---------------------------------------------------------------------------
# 2. _citation on a wikipedia Evidence
# ---------------------------------------------------------------------------

def test_citation_wikipedia():
    from src.services.chat.research import Evidence, _citation
    from src.services.chat.schemas.output import StoryCitation

    ev = Evidence(
        subject_id="qa",
        kind="wikipedia",
        text="t",
        meta={"title": "Chebyshev's inequality", "url": "http://x"},
    )
    cit = _citation(ev)
    assert isinstance(cit, StoryCitation)
    assert cit.kind == "wikipedia"
    assert cit.title == "Chebyshev's inequality"
    assert cit.url == "http://x"


# ---------------------------------------------------------------------------
# 3. Extension shims still expose the same names
# ---------------------------------------------------------------------------

def test_extension_research_shim_exports():
    from src.services.chat.agents.extension_agents.research import (  # noqa: F401
        Evidence,
        wiki_evidence,
    )


def test_extension_binder_shim_exports():
    from src.services.chat.agents.extension_agents.binder import (  # noqa: F401
        BulletDraft,
        bind_citations,
        _citation,
        _label,
    )
