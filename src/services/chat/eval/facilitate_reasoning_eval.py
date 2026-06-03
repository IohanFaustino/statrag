"""Offline A/B eval: facilitate map+teach WITH reasoning/CoT vs WITHOUT.

Compares the shipped facilitate map+teach (no reasoning) against a reasoning
variant that adds a hidden `reasoning` scratchpad field to BOTH the map stage
(key_points + concepts) and the teach stage (simplify rewrite). The reasoning is
parsed off and discarded — only the real fields are judged.

Eval-only: swaps prompts/schemas locally; does NOT modify the shipped pipeline.

Run manually (needs live API + Qdrant + hansen ch07 ingested):
    .venv/bin/python -m pytest src/services/chat/eval/facilitate_reasoning_eval.py \
        -m facilitate_reasoning -s
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

_OUT = Path(__file__).resolve().parents[4] / "docs" / "superpowers" / "eval" / "2026-06-03-facilitate-reasoning.md"
_PREVIEW = fac._PREVIEW
_SECTION_PREFIXES = ("7.2", "7.3", "7.4", "7.5")
_RUNS = 3

# --- reasoning-variant prompts (the proposed shipping prompts) -----------------

_MAP_REASONING_PROMPT = """<role>
You analyse one textbook section for a tutor.
</role>

<task>
Identify the section's essential teaching content. THINK before you commit.
</task>

<output_format>
Return ONLY a JSON object:
  "reasoning": 2-5 short sentences of private analysis — what is the section's
      single core teaching unit? which formulas have real derivation steps worth
      their own modal (NOT the central definition formula, NOT a bare inline
      expression)? which candidate concepts are near-duplicates to merge?
  "key_points": 3-6 short strings, the most important ideas (plain English).
  "concepts": array of {"term","kind","status"}; kind in
      "concept"|"theorem"|"formula"; status "explained" (defined in THIS section)
      or "referenced" (named but assumed/not defined here). Mark a formula as a
      concept ONLY when it has real derivation steps worth its own modal — NOT
      the section's central definition formula and NOT a bare inline expression.
      At most 5 concepts.
</output_format>

<rules>
Fill "reasoning" FIRST, then let it drive key_points/concepts.
English only — never copy garbled or non-English/OCR characters. For any
math use $...$ (inline) or $$...$$ (display); never \\( \\) or \\[ \\]. Do not invent terms.
Merge near-duplicate concepts into ONE (do not list a concept and its mere notation, or a term and its restatement, separately).
</rules>
"""

# Teach reasoning prompt = shipped teach rules, but wrapped to emit {reasoning, body}.
_TEACH_REASONING_PROMPT = fac.FACILITATE_TEACH_PROMPT.replace(
    "<output_format>",
    """<output_format>
Return ONLY a JSON object with two keys:
  "reasoning": 2-5 short sentences planning the lesson — the hook, the list of
      DISTINCT ideas (one paragraph each, no repeats), where each example goes,
      and which [[cN]] anchor lands at which first mention.
  "body": the markdown lesson body described below. Fill "reasoning" FIRST.

The "body" must be:""",
).replace("Return ONLY the markdown body.", 'Return ONLY the JSON object {"reasoning":..., "body":...}.')


# Pydantic schema with reasoning field (proposed FacilitateMap shape).
from pydantic import BaseModel, Field  # noqa: E402


class FacilitateMapReasoning(BaseModel):
    reasoning: str = ""
    key_points: list[str] = Field(default_factory=list)
    concepts: list[dict] = Field(default_factory=list)


class FacilitateTeachOut(BaseModel):
    reasoning: str = ""
    body: str = ""


_JUDGE = (
    "You score a learner-facing rewrite of a textbook section, 1-5 each (5=best):\n"
    "clarity, faithfulness (no claims the source lacks), keypoint_coverage,\n"
    "non_expansion (5 = clearly shorter/tighter than source; 1 = longer/padded),\n"
    "concept_id (did it anchor the right referenced concepts?).\n"
    "Return ONLY JSON: {\"clarity\":n,\"faithfulness\":n,\"keypoint_coverage\":n,"
    "\"non_expansion\":n,\"concept_id\":n}."
)


async def _map_reasoning(s, *, model):
    """Map stage WITH reasoning. Returns (key_points, concept_dicts)."""
    user = f"heading: {s.title}\n\nsection text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}"
    raw = await fac._chat(
        [{"role": "system", "content": _MAP_REASONING_PROMPT},
         {"role": "user", "content": user}],
        model=model, max_tokens=700, schema=FacilitateMapReasoning)
    data = json.loads(strip_fences(raw))
    kps = [str(x).strip() for x in (data.get("key_points") or []) if str(x).strip()][:fac._MAX_KEYPOINTS]
    concepts = []
    for c in (data.get("concepts") or [])[:fac._MAX_CONCEPTS]:
        term = str(c.get("term", "")).strip()
        if not term:
            continue
        kind = c.get("kind") if c.get("kind") in ("concept", "theorem", "formula") else "concept"
        status = "referenced" if c.get("status") == "referenced" else "explained"
        concepts.append({"term": term, "kind": kind, "status": status})
    return kps, concepts


async def _teach_reasoning(s, key_points, anchors, *, model):
    """Teach stage WITH reasoning. Returns body markdown (reasoning discarded)."""
    ids = "; ".join(f"{a.id}={a.term}" for a in anchors)
    user = (f"heading: {s.title}\nconcept ids: {ids}\nkey points: {key_points}\n\n"
            f"section text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}")
    raw = await fac._chat(
        [{"role": "system", "content": _TEACH_REASONING_PROMPT},
         {"role": "user", "content": user}],
        model=model, max_tokens=1000, schema=FacilitateTeachOut)
    data = json.loads(strip_fences(raw))
    return str(data.get("body") or "").strip()


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


@pytest.mark.facilitate_reasoning
def test_facilitate_reasoning_ab():
    async def run():
        model = settings.openai_model_nano
        secs = [s for s in fetch_chapter_sections("hansen", "ch07", max_sections=30)
                if any(s.title.startswith(p) for p in _SECTION_PREFIXES)]
        assert secs, "fixture sections not found (is hansen ch07 ingested?)"

        dims_keys = ("clarity", "faithfulness", "keypoint_coverage", "non_expansion", "concept_id")
        rows = {"baseline": {k: [] for k in dims_keys}, "reasoning": {k: [] for k in dims_keys}}
        samples: dict[str, dict[str, str]] = {}  # section_title -> {variant: body}

        for s in secs:
            src = s.chunk or s.excerpt or ""
            # build each variant's own map -> anchors -> teach
            for vname, map_fn, teach_fn in (
                ("baseline", fac._map_section, fac._teach),
                ("reasoning", _map_reasoning, _teach_reasoning),
            ):
                kps, cdicts = await map_fn(s, model=model)
                anchors = await fac._build_concepts(s, cdicts, explain_model=model)
                for run_i in range(_RUNS):
                    body = await teach_fn(s, kps, anchors, model=model)
                    sc = await _judge(src, body, model)
                    for k, v in sc.items():
                        rows[vname][k].append(v)
                    if run_i == 0:
                        samples.setdefault(s.title, {})[vname] = body

        means = {v: {k: round(statistics.mean(vals), 2) for k, vals in d.items()} for v, d in rows.items()}
        for v in means:
            means[v]["overall"] = round(statistics.mean(list(means[v].values())), 2)

        lines = ["# Facilitate map+teach — reasoning/CoT vs none (A/B)", "",
                 f"_hansen ch07 §7.2–7.5 · {_RUNS} runs/variant · LLM-judge (1–5) · judge={model}_", "",
                 "| variant | overall | clarity | faithfulness | keypoint_cov | non_expansion | concept_id |",
                 "|---|---|---|---|---|---|---|"]
        for v in ("baseline", "reasoning"):
            r = means[v]
            lines.append(f"| {v} | {r['overall']} | {r['clarity']} | {r['faithfulness']} | "
                         f"{r['keypoint_coverage']} | {r['non_expansion']} | {r['concept_id']} |")
        winner = max(means, key=lambda v: means[v]["overall"])
        delta = round(means["reasoning"]["overall"] - means["baseline"]["overall"], 2)
        lines += ["", f"**Winner:** {winner}  (reasoning − baseline = {delta:+})", "",
                  "## Sample bodies (run 1)", ""]
        for title, byv in samples.items():
            lines.append(f"### {title}")
            for v in ("baseline", "reasoning"):
                lines += [f"**{v}:**", "", byv.get(v, "_(none)_"), ""]

        _OUT.parent.mkdir(parents=True, exist_ok=True)
        _OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines[:12]))
        print(f"\nwrote {_OUT}")

    asyncio.run(run())
