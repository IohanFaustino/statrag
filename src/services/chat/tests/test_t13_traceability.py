"""T13 acceptance: traceability + structure + chat UI knobs."""
from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.services.chat import retrieval, router
from src.services.chat.schemas import ChatRequest, Source
from src.services.chat.schemas.output import TutorAnswer, TutorCitation


# ---------------------------------------------------------------------------
# T13-A: Source schema extended
# ---------------------------------------------------------------------------


def test_source_new_fields_defaults():
    s = Source(
        rank=1, book="islp", chapter="ch01", section="1.1",
        title="t", excerpt="e", score=0.5, chunkId="c-1", chunk="text",
        highlights=[],
    )
    assert s.book_name == ""
    assert s.authors == ""
    assert s.authors_short == ""
    assert s.year is None
    assert s.page_from is None
    assert s.page_to is None


def test_source_new_fields_round_trip():
    s = Source(
        rank=1, book="islp", chapter="ch02", section="2.1", title="t",
        excerpt="e", score=0.5, chunkId="c-1", chunk="text", highlights=[],
        book_name="An Introduction to Statistical Learning",
        authors="Gareth James, Daniela Witten",
        authors_short="James et al.",
        year=2023, page_from=15, page_to=18,
    )
    j = s.model_dump_json()
    s2 = Source.model_validate_json(j)
    assert s2.book_name == "An Introduction to Statistical Learning"
    assert s2.authors_short == "James et al."
    assert s2.year == 2023
    assert s2.page_from == 15
    assert s2.page_to == 18


# ---------------------------------------------------------------------------
# T13-B: _authors_short + _point_to_source
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", ""),
        ("Hayashi", "Hayashi"),
        ("Fumio Hayashi", "Hayashi"),
        ("James, Witten", "James et al."),
        ("Gareth James, Daniela Witten, Trevor Hastie, Robert Tibshirani", "James et al."),
        ("   ,   ,  ", ""),
    ],
)
def test_authors_short(raw, expected):
    assert retrieval._authors_short(raw) == expected


def test_safe_int_handles_minus_one_sentinel():
    assert retrieval._safe_int(-1) is None
    assert retrieval._safe_int(42) == 42
    assert retrieval._safe_int(None) is None
    assert retrieval._safe_int("not-a-number") is None
    assert retrieval._safe_int("12") == 12


def test_point_to_source_reads_full_payload():
    """T13-B: book_name, authors, year, page_from/to all flow through."""
    point = SimpleNamespace(
        id="c-1",
        score=0.83,
        payload={
            "book_slug": "islp",
            "book_name": "An Introduction to Statistical Learning",
            "authors": "Gareth James, Daniela Witten, Trevor Hastie, Robert Tibshirani",
            "year": 2023,
            "chapter_id": "ch02",
            "h2_path": "Statistical Learning | 2.1 What Is Statistical Learning?",
            "page_from": 15,
            "page_to": 18,
            "text": "Statistical learning refers to ...",
        },
    )
    s = retrieval._point_to_source(point, rank=1)
    assert s.book == "islp"
    assert s.book_name == "An Introduction to Statistical Learning"
    assert s.authors_short == "James et al."
    assert s.year == 2023
    assert s.page_from == 15
    assert s.page_to == 18
    assert s.chunk.startswith("Statistical learning")


def test_point_to_source_legacy_payload_still_works():
    """Old payloads without the new keys still produce a valid Source."""
    point = SimpleNamespace(
        id="c-1", score=0.5,
        payload={"book_slug": "islp", "chapter_id": "ch02", "text": "x"},
    )
    s = retrieval._point_to_source(point, rank=1)
    assert s.book_name == ""
    assert s.authors_short == ""
    assert s.year is None


def test_point_to_source_drops_minus_one_pages():
    """Ingestion writes -1 as 'missing' sentinel; we must not surface it."""
    point = SimpleNamespace(
        id="c-1", score=0.5,
        payload={
            "book_slug": "islp", "chapter_id": "ch02", "text": "x",
            "page_from": -1, "page_to": -1, "year": -1,
        },
    )
    s = retrieval._point_to_source(point, rank=1)
    assert s.page_from is None
    assert s.page_to is None
    assert s.year is None


# ---------------------------------------------------------------------------
# T13-C: retrieve tool payload enrichment
# ---------------------------------------------------------------------------


def test_retrieve_tool_payload_has_full_provenance(monkeypatch):
    import src.services.chat.tools.retrieve as retr_mod
    from src.services.chat import tools as tool_pkg

    fake_source = Source(
        rank=1, book="islp", chapter="ch02", section="2.1",
        title="Statistical Learning", excerpt="Statistical lear...",
        score=0.83, chunkId="c-1",
        chunk="Statistical learning refers to a vast set of tools for understanding data.",
        highlights=[],
        book_name="An Introduction to Statistical Learning",
        authors="Gareth James, Daniela Witten",
        authors_short="James et al.",
        year=2023, page_from=15, page_to=18,
    )
    monkeypatch.setattr(
        sys.modules["src.services.chat.tools.retrieve"],
        "hybrid_search",
        lambda *a, **kw: ([fake_source], SimpleNamespace()),
    )
    out = tool_pkg.retrieve.invoke({"query": "data-generating process"})
    payload = json.loads(out)
    item = payload[0]
    assert item["book_name"] == "An Introduction to Statistical Learning"
    assert item["authors_short"] == "James et al."
    assert item["year"] == 2023
    assert item["page_from"] == 15
    assert item["page_to"] == 18
    # T13-C: chunk text reaches the LLM (was previously only 200-char excerpt)
    assert "vast set of tools" in item["chunk"]


# ---------------------------------------------------------------------------
# T13-D: prompt constants
# ---------------------------------------------------------------------------


def test_tutor_prompt_demands_apa_citations():
    from src.services.chat.prompts.tutor import TUTOR_INSTRUCTIONS

    assert "authors_short" in TUTOR_INSTRUCTIONS
    assert "year" in TUTOR_INSTRUCTIONS
    assert "page_from" in TUTOR_INSTRUCTIONS
    assert "[1]" in TUTOR_INSTRUCTIONS or "[N]" in TUTOR_INSTRUCTIONS
    assert "## Sources" in TUTOR_INSTRUCTIONS


def test_tutor_prompt_demands_structure():
    from src.services.chat.prompts.tutor import TUTOR_INSTRUCTIONS

    # T18: structure now expressed via XML scaffold + markdown sections.
    assert "## " in TUTOR_INSTRUCTIONS  # H2 sections referenced in output_format
    assert "<rules>" in TUTOR_INSTRUCTIONS  # rules block scaffolded
    # No fabrication clause survives
    assert "fabricate" in TUTOR_INSTRUCTIONS.lower() or "never" in TUTOR_INSTRUCTIONS.lower()


def test_build_tutor_prompt_renders_apa_form():
    from src.services.chat.prompts.tutor import build_tutor_prompt

    s = Source(
        rank=1, book="islp", chapter="ch02", section="2.1",
        title="t", excerpt="e", score=0.83, chunkId="c-1",
        chunk="body", highlights=[],
        book_name="ISL", authors_short="James et al.", year=2023,
        page_from=15, page_to=18,
    )
    out = build_tutor_prompt([s])
    assert "James et al." in out
    assert "(2023)" in out
    assert "pp. 15–18" in out


# ---------------------------------------------------------------------------
# T13-E: TutorAnswer schema
# ---------------------------------------------------------------------------


def test_tutor_answer_schema_with_citations():
    ans = TutorAnswer(
        text="The DGP is the unknown mechanism.[1] It is rarely observed.[2]",
        sections=["Definition", "Why it matters"],
        citations=[
            TutorCitation(
                index=1, chunkId="c-1",
                authors_short="James et al.", year=2023,
                book_name="ISL", chapter="ch02", section="2.1",
                page_from=15, page_to=18,
                quote="The DGP is the unknown mechanism.",
            ),
            TutorCitation(
                index=2, chunkId="c-2",
                authors_short="Hayashi", year=2000,
                book_name="Econometrics", chapter="ch01", section="1.1",
                page_from=7, page_to=11,
                quote="It is rarely observed.",
            ),
        ],
    )
    j = ans.model_dump_json()
    ans2 = TutorAnswer.model_validate_json(j)
    assert len(ans2.citations) == 2
    assert ans2.citations[0].authors_short == "James et al."
    assert ans2.citations[1].year == 2000


def test_tutor_answer_json_schema_is_openai_compatible():
    schema = TutorAnswer.model_json_schema()
    assert schema["type"] == "object"
    assert "text" in schema["properties"]
    assert "citations" in schema["properties"]


def test_tutor_mode_impl_passes_response_format_when_flag_off(monkeypatch):
    """T13-E: TutorAnswer wired by default; TUTOR_FREE_TEXT=1 rolls back.

    Stubs both ``create_agent`` and ``get_async_checkpointer`` because the
    real async checkpointer needs an active event loop (see ADR-007 +
    checkpointer.py for the constraint).
    """
    from src.services.chat.mode_impls import tutor as tutor_mod

    captured: dict = {}

    def _fake_create_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    async def _fake_get_async_checkpointer():
        return SimpleNamespace()

    monkeypatch.setattr(tutor_mod, "create_agent", _fake_create_agent)
    monkeypatch.setattr(tutor_mod, "get_async_checkpointer", _fake_get_async_checkpointer)
    monkeypatch.delenv("TUTOR_FREE_TEXT", raising=False)
    tutor_mod.build_agent.cache_clear()
    asyncio.run(tutor_mod.build_agent())
    assert "response_format" in captured
    assert captured["response_format"] is TutorAnswer

    captured.clear()
    monkeypatch.setenv("TUTOR_FREE_TEXT", "1")
    tutor_mod.build_agent.cache_clear()
    asyncio.run(tutor_mod.build_agent())
    assert "response_format" not in captured
    tutor_mod.build_agent.cache_clear()


# ---------------------------------------------------------------------------
# T13-F: ChatRequest knobs
# ---------------------------------------------------------------------------


def test_chat_request_accepts_temperature_top_k_rerank():
    req = ChatRequest(
        message="x", mode="tutor", model="gpt-5.4-nano-2026-03-17",
        temperature=0.0, top_k=8, rerank=True,
    )
    assert req.temperature == 0.0
    assert req.top_k == 8
    assert req.rerank is True


def test_chat_request_temperature_out_of_range_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(message="x", mode="tutor", model="m", temperature=3.0)
    with pytest.raises(ValidationError):
        ChatRequest(message="x", mode="tutor", model="m", temperature=-0.1)


def test_chat_request_top_k_out_of_range_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(message="x", mode="tutor", model="m", top_k=0)
    with pytest.raises(ValidationError):
        ChatRequest(message="x", mode="tutor", model="m", top_k=99)


def test_chat_request_defaults_to_none():
    req = ChatRequest(message="x", mode="tutor", model="m")
    assert req.temperature is None
    assert req.top_k is None
    assert req.rerank is None


def test_tutor_router_threads_temperature_into_config(monkeypatch):
    """T13-F: when temperature is set, router puts it on configurable.model_kwargs."""

    captured_config = {}

    class _CaptureAgent:
        async def astream(self, inp, *, config, stream_mode):
            captured_config.update(config)
            yield "updates", {"final": {"structured_response": {
                "text": "x", "sections": [], "citations": [], "math_blocks": [], "figures": [],
            }}}

    from src.services.chat.mode_impls import tutor as tutor_mod
    async def _mk(): return _CaptureAgent()
    monkeypatch.setattr(tutor_mod, "build_agent", _mk)
    monkeypatch.setenv("TUTOR_DEEP_MODE", "0"); monkeypatch.setattr(router.settings, "use_v2_modes", ["tutor"], raising=False)

    req = ChatRequest(
        message="x", mode="tutor", model="gpt-5.4-nano-2026-03-17",
        temperature=0.0, conversationId="t-1",
    )

    async def _drive():
        async for _ in router.stream_chat(req):
            pass

    asyncio.run(_drive())
    assert captured_config["configurable"]["model_kwargs"]["temperature"] == 0.0


# ---------------------------------------------------------------------------
# T13-E end-to-end: structured_output emitted when TutorAnswer present
# ---------------------------------------------------------------------------


def test_tutor_v2_emits_structured_output_event(monkeypatch):
    schema_payload = {
        "text": "DGP is the unknown mechanism.[1]",
        "sections": ["Definition"],
        "citations": [{
            "index": 1, "chunkId": "c-1",
            "authors_short": "James et al.", "year": 2023,
            "book_name": "ISL", "chapter": "ch02", "section": "2.1",
            "page_from": 15, "page_to": 18,
            "quote": "DGP is the unknown mechanism.",
        }],
        "math_blocks": [], "figures": [],
    }

    class _StreamAgent:
        async def astream(self, inp, *, config, stream_mode):
            yield "messages", (SimpleNamespace(content="DGP is..."), {})
            yield "updates", {"final": {"structured_response": schema_payload}}

    from src.services.chat.mode_impls import tutor as tutor_mod
    async def _mk_stream(): return _StreamAgent()
    monkeypatch.setattr(tutor_mod, "build_agent", _mk_stream)
    monkeypatch.setenv("TUTOR_DEEP_MODE", "0"); monkeypatch.setattr(router.settings, "use_v2_modes", ["tutor"], raising=False)

    req = ChatRequest(message="x", mode="tutor", model="gpt-5.4-nano-2026-03-17")

    async def _drive():
        out = []
        async for ev in router.stream_chat(req):
            out.append(ev)
        return out

    events = asyncio.run(_drive())
    types = [e["type"] for e in events]
    assert "structured_output" in types
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "TutorAnswer"
    assert so["data"]["citations"][0]["authors_short"] == "James et al."
