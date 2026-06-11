"""Task 4 — seam guard wiring tests.

Tests for the ``_seam_guard`` helper in ``deep_tutor.py``:
  - one silent redraft on seam failure
  - second failure accepted (bounded to one retry)
  - passing seams skip redraft entirely
"""
import asyncio
import src.services.chat.agents.deep_tutor as dt
from src.services.chat.agents.seams import BEAT_ORDER


def test_seam_failure_triggers_one_redraft():
    calls = {"n": 0}
    bad = {k: "" for k in BEAT_ORDER}
    bad.update(definition="Bias is systematic error.",
               example_intuition="Photosynthesis happens in chloroplasts.")
    good = {k: "" for k in BEAT_ORDER}
    good.update(definition="Bias is systematic error in a model.",
                example_intuition="That same bias appears when a linear model misfits curves.")

    async def fake_redraft(**kw):
        calls["n"] += 1
        return None, good

    res_aspects, scores = asyncio.run(
        dt._seam_guard(bad, thesis="bias variance", redraft=fake_redraft)
    )
    assert calls["n"] == 1
    assert res_aspects["example_intuition"].startswith("That same bias")
    assert "seam_continuity" in scores


def test_second_failure_accepts_and_records():
    bad = {k: "" for k in BEAT_ORDER}
    bad.update(definition="Bias is error.",
               example_intuition="Photosynthesis in chloroplasts.")

    async def always_bad(**kw):
        return None, bad

    res_aspects, scores = asyncio.run(
        dt._seam_guard(bad, thesis="bias", redraft=always_bad)
    )
    assert scores["seam_continuity"] < 1.0


def test_passing_seams_no_redraft():
    calls = {"n": 0}
    good = {k: "" for k in BEAT_ORDER}
    good.update(definition="Bias is systematic error in a model.",
                example_intuition="That same bias appears when a linear model misfits curves.")

    async def fake_redraft(**kw):
        calls["n"] += 1
        return None, {}

    res_aspects, scores = asyncio.run(
        dt._seam_guard(good, thesis="bias", redraft=fake_redraft)
    )
    assert calls["n"] == 0
    assert scores["seam_continuity"] == 1.0
