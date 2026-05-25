"""Per-stage model override tests (About-model feature).

Covers the test categories requested for the feature:
- reliability: back-compat (no stageModels), garbage/unknown ignored
- integrity: non-overridable stages (embedding/vision) never re-routed;
  legacy single-model path intact
- relevance: an override actually reaches the stage that runs it
"""
from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")
os.environ.setdefault("TUTOR_DEEP_WARM", "0")
_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.services.chat.schemas import ChatRequest  # noqa: E402
from src.services.chat.agents import deep_tutor as dt  # noqa: E402
from src.core.config import settings  # noqa: E402

NANO = settings.openai_model_nano


# --- reliability --------------------------------------------------------
def test_request_back_compat_no_stage_models():
    req = ChatRequest(message="q", model="gpt-4o")
    assert req.stageModels is None  # legacy path unaffected


def test_unknown_model_ignored_falls_back():
    # draft override to a non-registry model -> default (the picker model)
    assert dt._resolve_stage_model("draft", "gpt-4o", {"draft": "not-a-real-model"}) == "gpt-4o"


def test_garbage_stage_key_ignored():
    assert dt._resolve_stage_model("expansion", "gpt-4o", {"bogus": "gpt-4o"}) == NANO


# --- integrity ----------------------------------------------------------
def test_non_overridable_stages_never_rerouted():
    # embedding + vision are not in the overridable set: an override is ignored
    assert dt._resolve_stage_model("embedding", "gpt-4o", {"embedding": "gpt-4o"}) == NANO
    assert dt._resolve_stage_model("vision", "gpt-4o", {"vision": "gpt-4o"}) == NANO
    assert "embedding" not in dt._OVERRIDABLE_STAGES
    assert "vision" not in dt._OVERRIDABLE_STAGES


def test_draft_default_is_picker_model_others_nano():
    # legacy intent: draft follows the picker model; cheap stages stay nano
    assert dt._resolve_stage_model("draft", "gpt-4o", None) == "gpt-4o"
    assert dt._resolve_stage_model("expansion", "gpt-4o", None) == NANO
    assert dt._resolve_stage_model("critique", "gpt-4o", None) == NANO


# --- relevance ----------------------------------------------------------
def test_valid_override_reaches_draft_stage(monkeypatch):
    """A stageModels['draft'] override is the model passed to _stream_draft."""
    captured: dict[str, str] = {}

    async def fake_draft(q, srcs, *, figures=None, on_aspect_delta=None, model=None, plan=None):
        captured["draft_model"] = model
        return None, {k: "" for k in dt.ASPECT_HEADINGS}

    async def fake_extract(q, *, model=None):
        captured["expansion_model"] = model
        return ["x"]

    async def fake_extract_ex(q, *, model=None, max_authors=4):
        # auto-diversity default routes concept extraction here
        captured["expansion_model"] = model
        return dt.QueryPlan(["x"], min(2, max_authors), [], [])

    async def fake_plan(q, srcs, *, model=None):
        captured["plan_model"] = model
        return None

    async def fake_wide(q, slugs, pool):
        from src.services.chat.schemas import RetrievalMetadata
        return [], RetrievalMetadata(
            rewrittenQuery=q, embedding="x", retrievalMs=1, collections=[],
            filter="", topK=0, scoreThreshold=0.0, mode="empty")

    def fake_density(*a, **kw):
        from src.services.chat.schemas import Source
        src = Source(
            rank=1, book="b", chapter="c", section="s", title="t",
            excerpt="bias variance", score=0.9, chunkId="cid", chunk="bias variance text",
        )
        return [src], ["col"]

    monkeypatch.setattr(dt, "_stream_draft", fake_draft)
    monkeypatch.setattr(dt, "extract_concepts", fake_extract)
    monkeypatch.setattr(dt, "extract_concepts_ex", fake_extract_ex)
    monkeypatch.setattr(dt, "build_synthesis_plan", fake_plan)
    monkeypatch.setattr(dt, "_wide_candidates", fake_wide)
    monkeypatch.setattr(dt, "_density_select", fake_density)

    # gpt-4o-mini is in the registry; expansion override stays nano-by-default
    req = ChatRequest(
        message="q", model="gpt-4o",
        stageModels={"draft": "gpt-4o-mini"},
    )

    async def _drain():
        return [e async for e in dt.run_deep_tutor(req)]

    asyncio.run(_drain())
    assert captured["draft_model"] == "gpt-4o-mini"      # override honored
    assert captured["expansion_model"] == NANO            # untouched stage stays nano
