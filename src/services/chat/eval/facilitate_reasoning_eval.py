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

_OUT = Path(__file__).resolve().parents[4] / "docs" / "superpowers" / "eval" / "2026-06-03-facilitate-reasoning-v2.md"
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
# v2: hardened against the v1 regressions (marker+term leak, plan-speak in
# blockquote, dropped LaTeX backslashes).
_TEACH_REASONING_PROMPT = fac.FACILITATE_TEACH_PROMPT.replace(
    "<output_format>",
    """<output_format>
Return ONLY a JSON object with two keys:
  "reasoning": 2-5 short sentences planning the lesson — the hook, the list of
      DISTINCT ideas (one paragraph each, no repeats), where each example goes,
      and which [[cN]] anchor lands at which first mention. This field is PRIVATE
      and discarded: NEVER let any planning words leak into "body".
  "body": the markdown lesson body described below. Fill "reasoning" FIRST, then
      write a clean "body" that obeys EVERY rule above as if reasoning never existed.

HARD GUARDS for "body" (these caused failures before):
  - A [[cN]] marker REPLACES the term word. NEVER write the term (or its formula)
    next to its marker. Wrong: "[[c1]] Weak Law of Large Numbers". Right: "the [[c1]]".
  - The definition blockquote must be the COMPLETE real definition in plain words.
    NEVER write meta/plan text like "the definition…", "the definition via…",
    "the definition of … condition". Wrong: "> **Term** the definition…".
    Right: "> **Term** <the actual statement of what it means>".
  - Keep all LaTeX backslashes: write $\\delta$, $\\varepsilon$, $\\sigma_n^2$ —
    never $delta$, $ varepsilon$, $ sigma$.

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

        lines = ["# Facilitate map+teach — reasoning/CoT vs none (A/B) — v2 hardened prompts", "",
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


# =============================================================================
# Model sweep: run the REASONING variant's produce stages (map+teach+explain)
# on nano vs qwen-plus vs deepseek-v4-pro. Judge fixed = nano (apples-to-apples).
# Captures token usage -> USD cost. Marker: facilitate_reasoning.
# =============================================================================

_SWEEP_OUT = Path(__file__).resolve().parents[4] / "docs" / "superpowers" / "eval" / "2026-06-03-facilitate-reasoning-models.md"
_SWEEP_MODELS = ("gpt-5.4-nano-2026-03-17", "qwen-plus",
                 "llama-3.3-70b-versatile", "gemini-2.5-flash")
_SWEEP_RUNS = 1  # 1 teach-run/section — deepseek latency is the bottleneck


async def _chat_usage(messages, *, model, max_tokens, schema=None):
    """Like fac._chat but also returns (in_tokens, out_tokens) for cost.

    NOTE: aclient_for() returns a RAW openai client for deepseek, bypassing the
    DeepSeekChat wrapper that disables thinking. Without re-injecting that
    extra_body here, deepseek-v4-pro would run with thinking ON (140-741s/call).
    """
    from src.services.chat.llm.router import aclient_for
    from src.services.chat.llm.structured import apply_structured_output
    oa = aclient_for(model)
    messages, response_format = apply_structured_output(messages, model, schema)
    kwargs = {"model": model, "messages": messages, "temperature": 0.0,
              "max_completion_tokens": max_tokens}
    if response_format is not None:
        kwargs["response_format"] = response_format
    if model.startswith("deepseek"):
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    resp = await oa.chat.completions.create(**kwargs)
    u = getattr(resp, "usage", None)
    it = int(getattr(u, "prompt_tokens", 0) or 0)
    ot = int(getattr(u, "completion_tokens", 0) or 0)
    return (resp.choices[0].message.content or ""), it, ot


async def _map_reasoning_usage(s, *, model):
    user = f"heading: {s.title}\n\nsection text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}"
    raw, it, ot = await _chat_usage(
        [{"role": "system", "content": _MAP_REASONING_PROMPT},
         {"role": "user", "content": user}], model=model, max_tokens=700, schema=FacilitateMapReasoning)
    try:
        data = json.loads(strip_fences(raw))
    except Exception:
        data = {}
    kps = [str(x).strip() for x in (data.get("key_points") or []) if str(x).strip()][:fac._MAX_KEYPOINTS]
    concepts = []
    for c in (data.get("concepts") or [])[:fac._MAX_CONCEPTS]:
        term = str(c.get("term", "")).strip()
        if not term:
            continue
        kind = c.get("kind") if c.get("kind") in ("concept", "theorem", "formula") else "concept"
        status = "referenced" if c.get("status") == "referenced" else "explained"
        concepts.append({"term": term, "kind": kind, "status": status})
    return kps, concepts, it, ot


async def _teach_reasoning_usage(s, key_points, anchors, *, model):
    ids = "; ".join(f"{a.id}={a.term}" for a in anchors)
    user = (f"heading: {s.title}\nconcept ids: {ids}\nkey points: {key_points}\n\n"
            f"section text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}")
    raw, it, ot = await _chat_usage(
        [{"role": "system", "content": _TEACH_REASONING_PROMPT},
         {"role": "user", "content": user}], model=model, max_tokens=1000, schema=FacilitateTeachOut)
    try:
        body = str(json.loads(strip_fences(raw)).get("body") or "").strip()
    except Exception:
        body = raw.strip()
    return body, it, ot


def _cheap_anchors(s, concept_dicts):
    """Build ConceptAnchors WITHOUT any retrieval/LLM (eval speed). Explanation
    is a short slice of the section text; only id+term+kind matter for teach."""
    from src.services.chat.schemas import ConceptAnchor, ConceptProvenance
    src = (s.chunk or s.excerpt or "")[:200]
    out = []
    for i, c in enumerate(concept_dicts, 1):
        out.append(ConceptAnchor(
            id=f"c{i}", term=c["term"], kind=c["kind"], explanation=src,
            provenance=ConceptProvenance(
                book_slug=s.book, book_name=s.book_name or s.book,
                authors_short=s.authors_short or "", section=s.title,
                page_from=s.page_from if s.page_from is not None else -1,
                page_to=s.page_to if s.page_to is not None else -1,
                chunk_id=s.chunkId, same_author=True, fallback=False)))
    return out


@pytest.mark.facilitate_reasoning
def test_facilitate_reasoning_model_sweep():
    async def run():
        import time
        from src.services.chat.cost import usd_est
        judge_model = settings.openai_model_nano  # also fixed for the EXPLAIN stage
        secs = [s for s in fetch_chapter_sections("hansen", "ch07", max_sections=30)
                if any(s.title.startswith(p) for p in _SECTION_PREFIXES)]
        assert secs, "fixture sections not found (is hansen ch07 ingested?)"
        dims_keys = ("clarity", "faithfulness", "keypoint_coverage", "non_expansion", "concept_id")

        results = {}  # model -> {means, usd, in, out, secs_per_call}
        samples = {}  # section -> {model: body}

        def _emit():
            """Write the report from whatever models have completed so far."""
            lines = ["# Facilitate reasoning variant — produce-model sweep (quality + cost)", "",
                     f"_hansen ch07 §7.2–7.5 · reasoning variant · {_SWEEP_RUNS} teach-run/section · "
                     f"judge+explain={judge_model} (fixed) · only MAP+TEACH use the swept model_", "",
                     "Cost = USD for the swept model's MAP+TEACH calls over these 4 sections "
                     "(explain billed to nano, excluded). Prices from `src/services/chat/cost.py`.", "",
                     "| produce model (map+teach) | overall | clarity | faith | keypt_cov | non_exp | "
                     "concept_id | in_tok | out_tok | USD (4 sec) | USD/section | s/call |",
                     "|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for m in _SWEEP_MODELS:
                if m not in results:
                    continue
                r = results[m]; mn = r["means"]; per = r["usd"] / max(len(secs), 1)
                lines.append(f"| {m} | {mn['overall']} | {mn['clarity']} | {mn['faithfulness']} | "
                             f"{mn['keypoint_coverage']} | {mn['non_expansion']} | {mn['concept_id']} | "
                             f"{r['in']} | {r['out']} | ${r['usd']:.4f} | ${per:.4f} | {r['spc']:.1f} |")
            lines += ["", "**Projection** (USD/section × 8-section chapter, map+teach only):"]
            for m in _SWEEP_MODELS:
                if m in results:
                    per = results[m]["usd"] / max(len(secs), 1)
                    lines.append(f"- {m}: ~${per * 8:.4f}/chapter")
            lines += ["", "## Sample teach bodies (run 1)", ""]
            for title, bym in samples.items():
                lines.append(f"### {title}")
                for m in _SWEEP_MODELS:
                    if m in results or m in bym:
                        lines += [f"**{m}:**", "", bym.get(m, "_(none)_"), ""]
            _SWEEP_OUT.parent.mkdir(parents=True, exist_ok=True)
            _SWEEP_OUT.write_text("\n".join(lines), encoding="utf-8")

        for model in _SWEEP_MODELS:
            dims = {k: [] for k in dims_keys}
            tot_in = tot_out = ncall = 0
            t_model = time.time()
            for s in secs:
                src = s.chunk or s.excerpt or ""
                try:
                    kps, cdicts, mi, mo = await _map_reasoning_usage(s, model=model)
                except Exception as e:  # noqa: BLE001
                    print(f"[{model}] map FAILED on {s.title}: {e}")
                    kps, cdicts, mi, mo = [], [], 0, 0
                tot_in += mi; tot_out += mo; ncall += 1
                # Cheap anchors: NO retrieval / NO explain calls. The teach stage
                # only needs concept ids + terms; anchor explanations don't affect
                # the judged body. Building real anchors re-scrolls the whole book
                # per (section,model) and dominated runtime.
                anchors = _cheap_anchors(s, cdicts)
                for run_i in range(_SWEEP_RUNS):
                    try:
                        body, ti, to = await _teach_reasoning_usage(s, kps, anchors, model=model)
                    except Exception as e:  # noqa: BLE001
                        print(f"[{model}] teach FAILED on {s.title}: {e}")
                        body, ti, to = "", 0, 0
                    tot_in += ti; tot_out += to; ncall += 1
                    sc = await _judge(src, body, judge_model)
                    for k, v in sc.items():
                        dims[k].append(v)
                    if run_i == 0:
                        samples.setdefault(s.title, {})[model] = body
            means = {k: round(statistics.mean(v), 2) if v else 0.0 for k, v in dims.items()}
            means["overall"] = round(statistics.mean(list(means.values())), 2)
            usd = usd_est(model, input_tokens=tot_in, output_tokens=tot_out)
            spc = (time.time() - t_model) / max(ncall, 1)
            results[model] = {"means": means, "usd": usd, "in": tot_in, "out": tot_out, "spc": spc}
            _emit()  # persist after every model so partial results survive
            print(f"[done] {model}: overall={means['overall']} usd=${usd:.4f} {spc:.1f}s/call")

        print(f"\nwrote {_SWEEP_OUT}")

    asyncio.run(run())
