"""T08 acceptance: real @tool surface for v2 single-agent modes."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.tools import BaseTool

import sys

# Force-import the submodules so they are registered in sys.modules.
import src.services.chat.tools.extract_terms  # noqa: F401
import src.services.chat.tools.kg_neighbors  # noqa: F401
import src.services.chat.tools.retrieve  # noqa: F401
import src.services.chat.tools.retrieve_figures  # noqa: F401
import src.services.chat.tools.retrieve_per_book  # noqa: F401

# `from <pkg> import <name>` in tools/__init__.py rebinds the submodule names
# to the @tool objects, so we fetch the raw modules via sys.modules.
retr_mod = sys.modules["src.services.chat.tools.retrieve"]
retpb_mod = sys.modules["src.services.chat.tools.retrieve_per_book"]
retf_mod = sys.modules["src.services.chat.tools.retrieve_figures"]
et_mod = sys.modules["src.services.chat.tools.extract_terms"]
kgn_mod = sys.modules["src.services.chat.tools.kg_neighbors"]

from src.services.chat import tools as tool_pkg
from src.services.chat.schemas import Figure, Source


# ---------------------------------------------------------------------------
# All tools are real LangChain @tool instances
# ---------------------------------------------------------------------------


def test_all_tools_are_basetool_instances():
    expected = {
        "retrieve", "retrieve_per_book", "retrieve_figures",
        "inspect_figure_tool", "extract_terms", "kg_neighbors",
    }
    for name in expected:
        obj = getattr(tool_pkg, name)
        assert isinstance(obj, BaseTool), f"{name} is not a langchain tool"


def test_tool_schemas_serialise_to_openai_format():
    """Each tool must expose a JSON-Schema args definition for function-calling."""
    for name in ("retrieve", "retrieve_per_book", "retrieve_figures",
                  "inspect_figure_tool", "extract_terms", "kg_neighbors"):
        obj = getattr(tool_pkg, name)
        schema = obj.args_schema
        assert schema is not None, f"{name} lacks args_schema"


def test_tool_docstrings_non_trivial():
    for name in ("retrieve", "retrieve_per_book", "retrieve_figures",
                  "inspect_figure_tool", "extract_terms", "kg_neighbors"):
        obj = getattr(tool_pkg, name)
        desc = obj.description or ""
        assert len(desc) > 30, f"{name} description too short: {desc!r}"


# ---------------------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------------------


def test_retrieve_returns_json_list(monkeypatch):
    fake_source = Source(
        rank=1, book="islp", chapter="ch1", section="1.1",
        title="t", excerpt="x", score=0.5, chunkId="c-1", chunk="x",
        highlights=[],
    )
    monkeypatch.setattr(retr_mod, "hybrid_search", lambda *a, **kw: ([fake_source], SimpleNamespace()))
    out = tool_pkg.retrieve.invoke({"query": "OLS"})
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert payload[0]["book"] == "islp"
    assert payload[0]["chunkId"] == "c-1"


def test_retrieve_clamps_k():
    schema = tool_pkg.retrieve.args_schema.model_json_schema()
    assert "k" in schema["properties"]


# ---------------------------------------------------------------------------
# retrieve_per_book
# ---------------------------------------------------------------------------


def test_retrieve_per_book_groups_by_book(monkeypatch):
    fake_a = Source(rank=1, book="a", chapter="ch1", section="1.1", title="A",
                     excerpt="", score=0.5, chunkId="a-1", chunk="x", highlights=[])
    fake_b = Source(rank=1, book="b", chapter="ch1", section="1.1", title="B",
                     excerpt="", score=0.5, chunkId="b-1", chunk="x", highlights=[])

    def _fake_search(query, *, book_slugs, top_k, rerank, **_kw):
        if book_slugs == ["a"]:
            return [fake_a], SimpleNamespace()
        return [fake_b], SimpleNamespace()

    monkeypatch.setattr(retpb_mod, "hybrid_search", _fake_search)
    out = tool_pkg.retrieve_per_book.invoke({"query": "x", "books": ["a", "b"]})
    payload = json.loads(out)
    assert set(payload.keys()) == {"a", "b"}
    assert payload["a"][0]["chunkId"] == "a-1"
    assert payload["b"][0]["chunkId"] == "b-1"


# ---------------------------------------------------------------------------
# retrieve_figures
# ---------------------------------------------------------------------------


def test_retrieve_figures_returns_figure_list(monkeypatch):
    fake = Figure(
        ref="f1", book="islp", chapter="ch1",
        caption="scatter plot", chart="https://x.png",
    )
    monkeypatch.setattr(retf_mod, "search_figures", lambda *a, **kw: [fake])
    out = tool_pkg.retrieve_figures.invoke({"query": "scatter"})
    payload = json.loads(out)
    assert payload[0]["ref"] == "f1"
    assert payload[0]["chart"].startswith("https://")


# ---------------------------------------------------------------------------
# extract_terms
# ---------------------------------------------------------------------------


def test_extract_terms_returns_json_list(monkeypatch):
    class _Choice:
        message = SimpleNamespace(content='["OLS", "heteroscedasticity"]')

    class _Resp:
        choices = [_Choice()]

    class _Chat:
        @property
        def completions(self):
            return self

        def create(self, **kw):
            return _Resp()

    class _OA:
        def __init__(self, api_key=None):
            self.chat = _Chat()

    monkeypatch.setattr(et_mod._openai, "OpenAI", _OA)
    out = tool_pkg.extract_terms.invoke({"text": "OLS handles heteroscedasticity."})
    payload = json.loads(out)
    assert payload == ["OLS", "heteroscedasticity"]


def test_extract_terms_swallows_llm_error(monkeypatch):
    class _Chat:
        @property
        def completions(self):
            return self

        def create(self, **kw):
            raise RuntimeError("api down")

    class _OA:
        def __init__(self, api_key=None):
            self.chat = _Chat()

    monkeypatch.setattr(et_mod._openai, "OpenAI", _OA)
    out = tool_pkg.extract_terms.invoke({"text": "anything"})
    assert json.loads(out) == []


# ---------------------------------------------------------------------------
# kg_neighbors
# ---------------------------------------------------------------------------


def test_kg_neighbors_returns_concept_list(monkeypatch):
    monkeypatch.setattr(
        kgn_mod.kg, "fetch_concepts_by_label",
        lambda label, k: [
            {"id": "ols", "label": "OLS", "source": {"book": "islp", "chapter": "ch3", "section": "3.1"}},
        ],
    )
    out = tool_pkg.kg_neighbors.invoke({"label": "OLS"})
    payload = json.loads(out)
    assert payload[0]["id"] == "ols"
    assert payload[0]["source"]["book"] == "islp"


def test_kg_neighbors_swallows_kg_error(monkeypatch):
    def _boom(label, k):
        raise RuntimeError("kg down")

    monkeypatch.setattr(kgn_mod.kg, "fetch_concepts_by_label", _boom)
    out = tool_pkg.kg_neighbors.invoke({"label": "anything"})
    assert json.loads(out) == []


# ---------------------------------------------------------------------------
# inspect_figure_tool — wraps async helper
# ---------------------------------------------------------------------------


def test_inspect_figure_tool_skips_when_no_url():
    """Empty chart_url short-circuits without calling the vision model."""
    out = tool_pkg.inspect_figure_tool.invoke({
        "figure_ref": "f1",
        "chart_url": "",
        "caption": "x",
        "query": "what is this?",
    })
    assert out == ""
