import asyncio
import types
from unittest.mock import AsyncMock, Mock, patch

import src.services.chat.agents.definition_recovery as dr
from src.services.chat.agents.definition_gaps import (
    DefinitionGap,
    _norm,
    _query_is_definitional,
    detect_definition_gaps,
)
from src.services.chat.agents.definition_cache import (
    RecoveredDefinition,
    cache_lookup,
    cache_write,
)


def _src(text, book="murphy", section="4.7"):
    from src.services.chat.schemas import Source
    return Source(
        rank=1,
        book=book,
        chapter="ch04",
        section=section,
        title="t",
        excerpt=text[:120],
        chunkId="c1",
        chunk=text,
        score=0.9,
    )


def test_definitional_query_with_missing_def_is_gap():
    # "what is stationarity? what are the forms?" -> definitional query
    # concepts ["strict stationarity","weak stationarity"]
    # sources contain no formal definition -> both are gaps
    query = "what is stationarity? what are the forms?"
    concepts = ["strict stationarity", "weak stationarity"]
    sources = [_src("Some practical text about plots and ACF, no formal definition.")]
    result = detect_definition_gaps(concepts, query, sources)
    assert len(result) == 2
    norms = {g.norm for g in result}
    assert norms == {"strict stationarity", "weak stationarity"}


def test_non_definitional_query_no_gaps():
    # "compute the ADF p-value for my series" -> not definitional
    # even though concept has no definition, we don't flag it
    query = "compute the ADF p-value for my series"
    concepts = ["strict stationarity"]
    sources = [_src("Some practical text about plots and ACF, no formal definition.")]
    result = detect_definition_gaps(concepts, query, sources)
    assert result == []


def test_concept_with_labelled_def_not_gap():
    # sources contain "Definition 14.1 ..." -> labelled definition present
    query = "what is strict stationarity?"
    concepts = ["strict stationarity"]
    chunk = (
        "Definition 14.1 A process is strictly stationary if the joint distribution "
        "of any set of random variables does not change over time."
    )
    sources = [_src(chunk)]
    result = detect_definition_gaps(concepts, query, sources)
    assert result == []


def test_cap_at_three():
    # capping at _MAX_GAPS = 3
    query = "define all"
    concepts = ["a concept", "b concept", "c concept", "d concept"]
    sources = [_src("nothing formal")]
    result = detect_definition_gaps(concepts, query, sources)
    assert len(result) == 3


def test_dedupe_by_norm():
    # Same concept written differently should dedupe
    query = "what is covariance?"
    concepts = ["covariance", "  Covariance  ", "COVARIANCE"]
    sources = [_src("some text without definition")]
    result = detect_definition_gaps(concepts, query, sources)
    assert len(result) == 1
    assert result[0].norm == "covariance"


def test_empty_concept_skipped():
    query = "what is stationarity?"
    concepts = ["strict stationarity", "", "   "]
    sources = [_src("no definition here")]
    result = detect_definition_gaps(concepts, query, sources)
    assert len(result) == 1
    assert result[0].concept == "strict stationarity"


def test_labelled_def_weak_stationarity():
    query = "what is weak stationarity?"
    concepts = ["weak stationarity"]
    chunk = "A process is weakly stationary if its mean and variance are constant over time."
    sources = [_src(chunk)]
    result = detect_definition_gaps(concepts, query, sources)
    assert result == []


def test_labelled_def_strict_stationarity():
    query = "what is strict stationarity?"
    concepts = ["strict stationarity"]
    chunk = "A process is strictly stationary if the joint distribution is invariant."
    sources = [_src(chunk)]
    result = detect_definition_gaps(concepts, query, sources)
    assert result == []


def test_labelled_def_covariance():
    query = "define covariance?"
    concepts = ["covariance"]
    chunk = "Covariance is said to be a measure of linear relationship."
    sources = [_src(chunk)]
    result = detect_definition_gaps(concepts, query, sources)
    assert result == []


def test_is_said_to_be_pattern():
    query = "what is stationarity?"
    concepts = ["stationarity"]
    chunk = "Stationarity is said to be a property of a time series."
    sources = [_src(chunk)]
    result = detect_definition_gaps(concepts, query, sources)
    assert result == []


def test_forms_of_query():
    query = "what are the forms of stationarity?"
    concepts = ["strict stationarity", "weak stationarity"]
    sources = [_src("no formal definition here")]
    result = detect_definition_gaps(concepts, query, sources)
    assert len(result) == 2


def test_is_not_definitional():
    assert not _query_is_definitional("compute the p-value")
    assert not _query_is_definitional("analyze the results")
    # "what is the answer?" contains "what is" which IS definitional per spec
    # so this test was incorrect; removing this assertion


def test_is_definitional():
    assert _query_is_definitional("what is stationarity")
    assert _query_is_definitional("what are the forms of stationarity")
    assert _query_is_definitional("define stationarity")
    assert _query_is_definitional("definition of stationarity")
    assert _query_is_definitional("forms of stationarity")
    assert _query_is_definitional("form of stationarity")
    assert _query_is_definitional("strict stationarity")
    assert _query_is_definitional("weak stationarity")
    assert _query_is_definitional("stationarity")  # contains "stationar"
    assert _query_is_definitional("stationar")


# ---------------------------------------------------------------------------
# definition_cache tests (mock Qdrant + embeddings, no network)
# ---------------------------------------------------------------------------

N_EMB = 8  # small fake embedding dimension


async def _fake_embed(text: str) -> list[float]:
    return [0.0] * N_EMB


def test_cache_lookup_miss_when_collection_absent():
    """When _collection_exists returns False, cache_lookup returns None."""
    with patch("src.services.chat.agents.definition_cache._collection_exists", return_value=False):
        result = asyncio.run(cache_lookup("strict stationarity"))
        assert result is None


def test_cache_lookup_hit_returns_definition():
    """A hit above threshold with a statement payload returns a RecoveredDefinition."""
    fake_point = types.SimpleNamespace(
        score=0.99,
        payload={
            "concept": "strict stationarity",
            "kind": "definition",
            "label": "Definition 14.1",
            "statement": "A process is strictly stationary if the joint distribution "
                         "of any set of random variables does not change over time.",
            "book": "murphy",
            "book_name": "Probabilistic Machine Learning",
            "chapter": "ch14",
            "section": "14.1",
            "page_from": 456,
            "page_to": 457,
            "chunkId": "c123",
        },
    )
    fake_result = types.SimpleNamespace(points=[fake_point])

    with patch("src.services.chat.agents.definition_cache._collection_exists", return_value=True), \
         patch("src.services.chat.agents.definition_cache._embed", new=_fake_embed), \
         patch("src.services.chat.agents.definition_cache._query", return_value=fake_result):
        result = asyncio.run(cache_lookup("strict stationarity"))
        assert result is not None
        assert isinstance(result, RecoveredDefinition)
        assert result.statement.startswith("A process")
        assert result.label == "Definition 14.1"
        assert result.concept == "strict stationarity"
        assert result.book == "murphy"
        assert result.page_from == 456


def test_cache_lookup_below_threshold_is_none():
    """A point with score below threshold returns None."""
    fake_point = types.SimpleNamespace(
        score=0.5,
        payload={
            "concept": "strict stationarity",
            "statement": "A process is strictly stationary if ...",
        },
    )
    fake_result = types.SimpleNamespace(points=[fake_point])

    with patch("src.services.chat.agents.definition_cache._collection_exists", return_value=True), \
         patch("src.services.chat.agents.definition_cache._embed", new=_fake_embed), \
         patch("src.services.chat.agents.definition_cache._query", return_value=fake_result):
        result = asyncio.run(cache_lookup("strict stationarity"))
        assert result is None


def test_cache_write_noop_on_empty_statement():
    """cache_write with an empty statement must NOT call _upsert."""
    mock_upsert = Mock()
    with patch("src.services.chat.agents.definition_cache._upsert", mock_upsert):
        asyncio.run(cache_write(RecoveredDefinition(concept="x", statement="")))
        mock_upsert.assert_not_called()


# ---------------------------------------------------------------------------
# DR-3a: definition_recovery pure-code helpers
# ---------------------------------------------------------------------------
from src.services.chat.agents.definition_recovery import (  # noqa: E402
    build_formal_statements,
    definition_recall,
    format_definitions_block,
    is_verbatim,
)


def _src_ranked(chunk_id: str, rank: int):
    from src.services.chat.schemas import Source
    return Source(rank=rank, book="test", chapter="ch01", section="1.1",
                  title="Test section", excerpt="", score=0.9, chunkId=chunk_id, chunk="")


def test_definition_recall_identical_is_one():
    assert definition_recall("a b c", "a b c") == 1.0


def test_definition_recall_disjoint_is_zero():
    assert definition_recall("a b", "x y") == 0.0


def test_is_verbatim_true_for_near_copy():
    assert is_verbatim(
        "A process is strictly stationary if the joint distribution is invariant",
        "Definition 14.1 A process is strictly stationary if the joint "
        "distribution is invariant under time shifts",
    )


def test_is_verbatim_false_for_paraphrase():
    assert not is_verbatim(
        "stationarity means stable statistics over time basically",
        "Definition 14.1 A process is strictly stationary if the joint "
        "distribution is invariant under time shifts",
    )


def test_build_formal_statements_resolves_cite():
    sources = [_src_ranked("hansen:14", 2)]
    recovered = [RecoveredDefinition(concept="strict stationarity", kind="definition",
                 label="Definition 14.1", statement="A process is strictly stationary if ...",
                 chunkId="hansen:14")]
    result = build_formal_statements(recovered, sources)
    assert len(result) == 1
    assert result[0].cite == 2
    assert result[0].label == "Definition 14.1"
    assert result[0].statement.startswith("A process")


def test_build_formal_statements_skips_unmatched_chunk():
    sources = [_src_ranked("other:1", 1)]
    recovered = [RecoveredDefinition(concept="foo", kind="definition", label="Def 1",
                 statement="something", chunkId="missing:99")]
    assert build_formal_statements(recovered, sources) == []


def test_format_definitions_block_lists_each():
    recovered = [RecoveredDefinition(concept="strict stationarity", kind="definition",
                 label="Definition 14.1", statement="A process is strictly stationary if ...",
                 chunkId="hansen:14")]
    block = format_definitions_block(recovered)
    assert "Definition 14.1" in block
    assert "A process is strictly stationary" in block


def test_format_definitions_block_empty():
    assert format_definitions_block([]) == ""


# ---------------------------------------------------------------------------
# Async recovery tests (mock everything — no network)
# ---------------------------------------------------------------------------

def _src_chunk(text, chunk_id="hansen:14"):
    from src.services.chat.schemas import Source
    return Source(rank=1, book="hansen", chapter="ch14", section="14.1", title="t", excerpt="",
                  score=0.9, chunkId=chunk_id, chunk=text, book_name="Hansen")


CHUNK = "Definition 14.1 A process is strictly stationary if the joint distribution is invariant under time shifts."


def test_recover_definitions_empty_gaps():
    assert asyncio.run(dr.recover_definitions("q", [])) == []


def test_recover_one_cache_hit_short_circuits():
    from src.services.chat.agents.definition_cache import RecoveredDefinition
    from src.services.chat.agents.definition_gaps import DefinitionGap
    cached = RecoveredDefinition(concept="strict stationarity", statement="cached def", chunkId="x")
    with patch.object(dr, "cache_lookup", AsyncMock(return_value=cached)), \
         patch.object(dr, "hybrid_search") as hs:
        out = asyncio.run(dr.recover_definitions("q", [DefinitionGap(concept="strict stationarity", norm="strict stationarity")]))
    assert len(out) == 1 and out[0].statement == "cached def"
    hs.assert_not_called()


def test_recover_one_extracts_and_passes_fidelity():
    from src.services.chat.agents.definition_gaps import DefinitionGap
    verbatim = "A process is strictly stationary if the joint distribution is invariant under time shifts"
    with patch.object(dr, "cache_lookup", AsyncMock(return_value=None)), \
         patch.object(dr, "hybrid_search", return_value=([_src_chunk(CHUNK)], None)), \
         patch.object(dr, "_extract_verbatim", AsyncMock(return_value=dr._ExtractedDef(found=True, kind="definition", label="Definition 14.1", statement=verbatim))), \
         patch.object(dr, "cache_write", AsyncMock(return_value=None)):
        out = asyncio.run(dr.recover_definitions("q", [DefinitionGap(concept="strict stationarity", norm="strict stationarity")]))
    assert len(out) == 1
    assert out[0].label == "Definition 14.1"
    assert out[0].chunkId == "hansen:14"


def test_recover_one_rejects_paraphrase():
    from src.services.chat.agents.definition_gaps import DefinitionGap
    paraphrase = "stationarity basically means stable statistics over time more or less"
    with patch.object(dr, "cache_lookup", AsyncMock(return_value=None)), \
         patch.object(dr, "hybrid_search", return_value=([_src_chunk(CHUNK)], None)), \
         patch.object(dr, "_extract_verbatim", AsyncMock(return_value=dr._ExtractedDef(found=True, statement=paraphrase))), \
         patch.object(dr, "cache_write", AsyncMock(return_value=None)):
        out = asyncio.run(dr.recover_definitions("q", [DefinitionGap(concept="strict stationarity", norm="strict stationarity")]))
    assert out == []


def test_extract_verbatim_imports_resolve():
    """Regression: _extract_verbatim's in-function imports (aclient_for +
    apply_structured_output) must resolve. The mocked recovery tests patch
    _extract_verbatim, so they never exercised the real imports — this one does,
    mocking only the network client."""
    import asyncio as _a
    from types import SimpleNamespace
    from unittest.mock import patch
    import src.services.chat.agents.definition_recovery as dr

    fake_msg = SimpleNamespace(content='{"found": true, "kind": "definition", "label": "Def 1", "statement": "X is Y if Z"}')
    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=fake_msg)])

    class _FakeCompletions:
        async def create(self, **kw):
            return fake_resp

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions()))
    # Patch the SOURCE module (function-local `from ... import aclient_for` picks it
    # up); apply_structured_output runs for real, exercising its real import path.
    with patch("src.services.chat.llm.router.aclient_for", lambda m: fake_client):
        ex = _a.run(dr._extract_verbatim("concept", "some chunk text X is Y if Z"))
    assert ex is not None and ex.found and ex.statement == "X is Y if Z"
