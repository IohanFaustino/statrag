"""T22 (E6): tutor citation reconciler.

The LLM occasionally numbers inline `[N]` markers using the retrieve
tool's `rank` (1..10) instead of a 1-based citation index that lines up
with the `citations` array. The reconciler:

- renumbers `[N]` markers to 1, 2, 3, … in order of first appearance,
- renumbers `citations[i].index` to match,
- drops citations that have no matching marker,
- strips markers that have no matching citation.
"""
from __future__ import annotations

from src.services.chat.router import _reconcile_tutor_citations


def _c(index: int, label: str) -> dict:
    return {
        "index": index,
        "chunkId": label,
        "authors_short": label,
        "year": None,
        "book_name": label,
        "chapter": "",
        "section": "",
        "page_from": None,
        "page_to": None,
        "quote": "",
    }


def test_renumber_to_sequential_in_order_of_appearance():
    """LLM cited [6], [8], [5] — renumber to [1], [2], [3]."""
    payload = {
        "text": "DGP is the process.[6] It is stochastic.[8] Inference uses it.[5]",
        "citations": [_c(5, "A"), _c(6, "B"), _c(8, "C")],
    }
    out = _reconcile_tutor_citations(payload)
    # Markers renumbered by order of first inline appearance: [6]→1, [8]→2, [5]→3
    assert out["text"] == "DGP is the process.[1] It is stochastic.[2] Inference uses it.[3]"
    indices = [c["index"] for c in out["citations"]]
    assert indices == [1, 2, 3]
    # New citation 1 is the LLM's old 6 → was chunkId="B"
    assert out["citations"][0]["chunkId"] == "B"
    assert out["citations"][1]["chunkId"] == "C"
    assert out["citations"][2]["chunkId"] == "A"


def test_drop_orphan_citations_no_marker():
    """Citations 3, 4 have no inline marker → drop them."""
    payload = {
        "text": "DGP is stochastic.[2]",
        "citations": [_c(1, "A"), _c(2, "B"), _c(3, "C"), _c(4, "D")],
    }
    out = _reconcile_tutor_citations(payload)
    assert len(out["citations"]) == 1
    assert out["citations"][0]["chunkId"] == "B"
    assert out["citations"][0]["index"] == 1
    assert out["text"] == "DGP is stochastic.[1]"


def test_strip_orphan_markers_no_citation():
    """Markers [6], [8] have no matching citation → strip them."""
    payload = {
        "text": "DGP is stochastic.[2] Then more.[6] And more.[8] End.[2]",
        "citations": [_c(2, "B")],
    }
    out = _reconcile_tutor_citations(payload)
    assert out["text"] == "DGP is stochastic.[1] Then more. And more. End.[1]"
    assert len(out["citations"]) == 1


def test_reuse_same_marker_keeps_one_citation():
    """Two `[N]` markers for the same source produce one citation entry."""
    payload = {
        "text": "First fact.[2] Second fact.[2]",
        "citations": [_c(2, "B")],
    }
    out = _reconcile_tutor_citations(payload)
    assert out["text"] == "First fact.[1] Second fact.[1]"
    assert len(out["citations"]) == 1


def test_passthrough_when_no_text():
    """Missing or non-string text returns payload unchanged."""
    payload = {"citations": [_c(1, "A")]}
    assert _reconcile_tutor_citations(payload) == payload


def test_passthrough_when_no_citations():
    """Empty citations array returns payload unchanged."""
    payload = {"text": "DGP.[1]", "citations": []}
    out = _reconcile_tutor_citations(payload)
    assert out == payload


def test_already_consistent_payload_unchanged():
    """A well-formed payload should round-trip unchanged."""
    payload = {
        "text": "First.[1] Second.[2] First again.[1]",
        "citations": [_c(1, "A"), _c(2, "B")],
    }
    out = _reconcile_tutor_citations(payload)
    assert out["text"] == payload["text"]
    assert [c["index"] for c in out["citations"]] == [1, 2]
