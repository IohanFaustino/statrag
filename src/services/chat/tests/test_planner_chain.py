"""Unit tests for the chained question-decomposition query planner."""
import asyncio
import pytest
from src.services.chat.prompts import deep_tutor as P
from src.services.chat.agents import deep_tutor as DT


def test_chain_prompts_exist_and_mention_keys():
    assert "sub_questions" in P.PLANNER_DECOMPOSE_PROMPT
    assert "application" in P.PLANNER_DECOMPOSE_PROMPT.lower()
    assert "related" in P.PLANNER_DECOMPOSE_PROMPT.lower()
    assert "items" in P.PLANNER_EXPAND_PROMPT
    for k in ("concept", "query", "facet"):
        assert k in P.PLANNER_EXPAND_PROMPT
    for k in ("concepts", "perspectives", "facets", "queries"):
        assert k in P.PLANNER_CONSOLIDATE_PROMPT
    assert "{max_authors}" in P.PLANNER_CONSOLIDATE_PROMPT


def test_parse_decompose_clamps_and_strips():
    raw = '```json\n{"sub_questions":["a"," b ","","c","d","e","f"]}\n```'
    assert DT._parse_decompose(raw) == ["a", "b", "c", "d", "e"]


def test_parse_decompose_empty_raises():
    with pytest.raises(ValueError):
        DT._parse_decompose('{"sub_questions": []}')


def test_parse_expand_items():
    raw = '{"items":[{"sub_question":"q1","concept":"bias","query":"bias formula","facet":"bias def"}]}'
    items = DT._parse_expand(raw)
    assert items == [{"sub_question": "q1", "concept": "bias", "query": "bias formula", "facet": "bias def"}]


def test_parse_expand_empty_raises():
    with pytest.raises(ValueError):
        DT._parse_expand('{"items": []}')


def test_parse_consolidate_builds_queryplan_and_clamps():
    raw = ('{"concepts":["a","b","c","d"],"perspectives":9,'
           '"facets":["f1","f2","f3","f4","f5","f6","f7"],'
           '"queries":["q1","q2","q3","q4","q5","q6"]}')
    plan = DT._parse_consolidate(raw, max_authors=4)
    assert plan.concepts == ["a", "b", "c"]
    assert plan.suggested_authors == 4
    assert plan.facets == ["f1", "f2", "f3", "f4", "f5", "f6"]
    assert plan.queries == ["q1", "q2", "q3", "q4", "q5"]


def test_parse_consolidate_no_queries_raises():
    with pytest.raises(ValueError):
        DT._parse_consolidate('{"concepts":["a"],"perspectives":1,"facets":["f"],"queries":[]}', max_authors=4)


def test_extract_concepts_chain_composes_steps(monkeypatch):
    async def fake_decompose(q, *, model):
        return ["sq1", "sq2"]

    async def fake_expand(q, subqs, *, model):
        assert subqs == ["sq1", "sq2"]
        return [{"sub_question": "sq1", "concept": "c", "query": "qq", "facet": "ff"}]

    async def fake_consolidate(items, *, model, max_authors):
        assert items and items[0]["concept"] == "c"
        return DT.QueryPlan(["c"], 2, ["qq"], ["ff"])

    monkeypatch.setattr(DT, "_planner_decompose", fake_decompose)
    monkeypatch.setattr(DT, "_planner_expand", fake_expand)
    monkeypatch.setattr(DT, "_planner_consolidate", fake_consolidate)
    plan = asyncio.run(DT.extract_concepts_chain("the question", model=None, max_authors=4))
    assert plan == DT.QueryPlan(["c"], 2, ["qq"], ["ff"])


def test_dispatcher_flag_off_uses_single(monkeypatch):
    async def fake_single(q, *, model, max_authors):
        return DT.QueryPlan(["single"], 1, ["sq"], ["sf"])

    async def boom_chain(q, *, model, max_authors):
        raise AssertionError("chain must NOT run when flag off")

    monkeypatch.setattr(DT, "_PLANNER_CHAIN_ON", False)
    monkeypatch.setattr(DT, "_extract_concepts_single", fake_single)
    monkeypatch.setattr(DT, "extract_concepts_chain", boom_chain)
    plan = asyncio.run(DT.extract_concepts_ex("q", model=None, max_authors=4))
    assert plan.concepts == ["single"]


def test_dispatcher_flag_on_uses_chain(monkeypatch):
    async def fake_single(q, *, model, max_authors):
        return DT.QueryPlan(["single"], 1, ["sq"], ["sf"])

    async def fake_chain(q, *, model, max_authors):
        return DT.QueryPlan(["chain"], 2, ["cq"], ["cf"])

    monkeypatch.setattr(DT, "_PLANNER_CHAIN_ON", True)
    monkeypatch.setattr(DT, "_extract_concepts_single", fake_single)
    monkeypatch.setattr(DT, "extract_concepts_chain", fake_chain)
    plan = asyncio.run(DT.extract_concepts_ex("q", model=None, max_authors=4))
    assert plan.concepts == ["chain"]


def test_dispatcher_chain_failure_falls_back_to_single(monkeypatch):
    async def fake_single(q, *, model, max_authors):
        return DT.QueryPlan(["single"], 1, ["sq"], ["sf"])

    async def fail_chain(q, *, model, max_authors):
        raise RuntimeError("chain blew up")

    monkeypatch.setattr(DT, "_PLANNER_CHAIN_ON", True)
    monkeypatch.setattr(DT, "_extract_concepts_single", fake_single)
    monkeypatch.setattr(DT, "extract_concepts_chain", fail_chain)
    plan = asyncio.run(DT.extract_concepts_ex("q", model=None, max_authors=4))
    assert plan.concepts == ["single"]


def test_dispatcher_empty_query_short_circuits():
    plan = asyncio.run(DT.extract_concepts_ex("   ", model=None, max_authors=4))
    assert plan == DT.QueryPlan([], 1, [], [])
