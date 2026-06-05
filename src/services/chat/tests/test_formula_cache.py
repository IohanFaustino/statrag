import asyncio
import src.services.chat.agents.formula_cache as fc
from src.services.chat.agents.formula_cache import RecoveredEquation


class _Pt:
    def __init__(self, score, payload): self.score = score; self.payload = payload


def test_lookup_returns_hit_above_threshold(monkeypatch):
    monkeypatch.setattr(fc, "_embed", _fake_embed)
    monkeypatch.setattr(fc, "_collection_exists", lambda name: True)
    class _Res:
        points = [_Pt(0.97, {"term": "bias", "latex": "$E[\\hat\\theta]-\\theta$", "citation": "Murphy"})]
    monkeypatch.setattr(fc, "_query", lambda name, emb, limit: _Res())
    out = asyncio.run(fc.cache_lookup("bias of an estimator"))
    assert out is not None and out.latex == "$E[\\hat\\theta]-\\theta$"


def test_lookup_miss_below_threshold(monkeypatch):
    monkeypatch.setattr(fc, "_embed", _fake_embed)
    monkeypatch.setattr(fc, "_collection_exists", lambda name: True)
    class _Res:
        points = [_Pt(0.50, {"term": "bias", "latex": "$x$", "citation": "c"})]
    monkeypatch.setattr(fc, "_query", lambda name, emb, limit: _Res())
    assert asyncio.run(fc.cache_lookup("bias")) is None


def test_lookup_miss_when_collection_absent(monkeypatch):
    monkeypatch.setattr(fc, "_collection_exists", lambda name: False)
    assert asyncio.run(fc.cache_lookup("bias")) is None


def test_write_is_best_effort_on_error(monkeypatch):
    monkeypatch.setattr(fc, "_embed", _fake_embed)
    def boom(*a, **k): raise RuntimeError("qdrant down")
    monkeypatch.setattr(fc, "_upsert", boom)
    # must not raise
    asyncio.run(fc.cache_write("bias", "$x$", "Murphy"))


async def _fake_embed(text): return [0.1] * 8
