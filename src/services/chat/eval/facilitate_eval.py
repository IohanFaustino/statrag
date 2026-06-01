"""Offline LLM-judge eval for the facilitate teach node.

Runs the teach step on hansen ch07 (sections 7.1-7.4) across prompt variants,
scores each with an LLM-as-judge on clarity / faithfulness / key-point coverage /
non-expansion / concept-id quality (1-5), 3 runs each, and writes a ranked table.

Run manually (needs live API):
    .venv/bin/python -m pytest src/services/chat/eval/facilitate_eval.py -m facilitate_eval -s
"""
from __future__ import annotations

import asyncio
import json
import statistics
from pathlib import Path

import pytest

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.agents import facilitate as fac
from src.services.chat.retrieval import fetch_chapter_sections

_OUT = Path(__file__).resolve().parents[4] / "docs" / "superpowers" / "eval" / "2026-06-01-facilitate-variants.md"

# Variant teach prompts to compare. v1 = the shipped prompt; v2 = stricter bullets.
_VARIANTS = {
    "v1_shipped": fac.FACILITATE_TEACH_PROMPT,
    "v2_bullets_strict": (
        "Rewrite this section for a learner as a SHORT study note.\n"
        "- Lead with ONE plain sentence.\n"
        "- Then a bullet list of ONLY the key points (<=6 bullets, <=20 words each).\n"
        "- Simpler words. Never longer than the source. No background prose.\n"
        "- Put every concept's detail in its anchor, not the body.\n"
        "- Insert [[cN]] after each listed concept's first mention.\n"
        "Return ONLY markdown."
    ),
}

_JUDGE = (
    "You score a learner-facing rewrite of a textbook section, 1-5 each (5=best):\n"
    "clarity, faithfulness (no claims the source lacks), keypoint_coverage,\n"
    "non_expansion (5 = clearly shorter/tighter than source; 1 = longer/padded),\n"
    "concept_id (did it anchor the right referenced concepts?).\n"
    "Return ONLY JSON: {\"clarity\":n,\"faithfulness\":n,\"keypoint_coverage\":n,"
    "\"non_expansion\":n,\"concept_id\":n}."
)


async def _teach_with_prompt(section, key_points, anchors, prompt, model):
    # temporarily swap the module prompt the teach node reads
    orig = fac.FACILITATE_TEACH_PROMPT
    fac.FACILITATE_TEACH_PROMPT = prompt
    try:
        return await fac._teach(section, key_points, anchors, model=model)
    finally:
        fac.FACILITATE_TEACH_PROMPT = orig


async def _judge(section_text, body, model):
    raw = await fac._chat(
        [{"role": "system", "content": _JUDGE},
         {"role": "user", "content": f"SOURCE:\n{section_text[:2000]}\n\nREWRITE:\n{body}"}],
        model=model, max_tokens=120)
    try:
        d = json.loads(strip_fences(raw))
        return {k: float(d.get(k, 0)) for k in ("clarity", "faithfulness", "keypoint_coverage", "non_expansion", "concept_id")}
    except Exception:
        return {k: 0.0 for k in ("clarity", "faithfulness", "keypoint_coverage", "non_expansion", "concept_id")}


@pytest.mark.facilitate_eval
def test_facilitate_variant_ranking():
    async def run():
        model = settings.openai_model_nano
        secs = [s for s in fetch_chapter_sections("hansen", "ch07", max_sections=30)
                if any(s.title.startswith(p) for p in ("7.1", "7.2", "7.3", "7.4"))]
        assert secs, "fixture sections not found (is hansen ch07 ingested?)"
        # build maps once per section (shared across variants)
        prepared = []
        for s in secs:
            kps, cdicts = await fac._map_section(s, model=model)
            anchors = await fac._build_concepts(s, cdicts, explain_model=model)
            prepared.append((s, kps, anchors))
        rows = {}
        for vname, vprompt in _VARIANTS.items():
            dims = {k: [] for k in ("clarity", "faithfulness", "keypoint_coverage", "non_expansion", "concept_id")}
            for _run in range(3):
                for s, kps, anchors in prepared:
                    body = await _teach_with_prompt(s, kps, anchors, vprompt, model)
                    sc = await _judge(s.chunk or s.excerpt or "", body, model)
                    for k, v in sc.items():
                        dims[k].append(v)
            rows[vname] = {k: round(statistics.mean(v), 2) for k, v in dims.items()}
            rows[vname]["overall"] = round(statistics.mean([statistics.mean(v) for v in dims.values()]), 2)
        # write ranked table
        _OUT.parent.mkdir(parents=True, exist_ok=True)
        ranked = sorted(rows.items(), key=lambda kv: kv[1]["overall"], reverse=True)
        lines = ["# Facilitate teach-prompt variants — eval", "",
                 "_hansen ch07 §7.1–7.4 · 3 runs/variant · LLM-judge (1–5)_", "",
                 "| variant | overall | clarity | faithfulness | keypoint_cov | non_expansion | concept_id |",
                 "|---|---|---|---|---|---|---|"]
        for name, r in ranked:
            lines.append(f"| {name} | {r['overall']} | {r['clarity']} | {r['faithfulness']} | "
                         f"{r['keypoint_coverage']} | {r['non_expansion']} | {r['concept_id']} |")
        lines += ["", f"**Winner:** {ranked[0][0]}"]
        _OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
    asyncio.run(run())
