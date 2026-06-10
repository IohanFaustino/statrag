"""Extension v2 LLM nodes. Each node = harness (prompt + structured schema)
+ model (resolve_stage_model). One parse retry, then graceful degradation."""
from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.core.config import settings

from ._models import resolve_stage_model, resolve_stage_temperature
from .prompts import (EDITOR_PROMPT, JUDGE_PROMPT, MINER_PROMPT,
                      STORYTELLER_PROMPT, WRITER_PROMPT)
from .binder import BulletDraft
from .research import Evidence


# ── structured-output schemas (LLM-facing) ──────────────────────────────────
class TakeDraft(BaseModel):
    idx: int = 0
    heading: str
    story: str
    key_items: list[str] = Field(default_factory=list)
    degraded: bool = False


class TakeDraftList(BaseModel):
    takes: list[TakeDraft]


class Subject(BaseModel):
    id: str = ""
    take_idx: int = 0
    title: str
    tag: str = "formal-def"
    queries: list[str] = Field(default_factory=list)


class SubjectList(BaseModel):
    subjects: list[Subject]


class WriterBullet(BaseModel):
    subject: str
    body: str
    evidence_ids: list[str] = Field(default_factory=list)


class WriterOut(BaseModel):
    bullets: list[WriterBullet]


class JudgeOut(BaseModel):
    failed_subjects: list[str] = Field(default_factory=list)


# ── invocation helper (patched in tests) ────────────────────────────────────
async def _ainvoke(stage: str, schema, system: str, user: str, stage_models):
    llm = ChatOpenAI(model=resolve_stage_model(stage, stage_models),
                     temperature=resolve_stage_temperature(stage),
                     api_key=settings.openai_api_key,
                     max_retries=6).with_structured_output(schema)
    return await llm.ainvoke([{"role": "system", "content": system},
                              {"role": "user", "content": user}])


async def _with_retry(stage, schema, system, user, stage_models):
    try:
        return await _ainvoke(stage, schema, system, user, stage_models)
    except Exception:  # noqa: BLE001 — one repair retry
        return await _ainvoke(stage, schema, system,
                              user + "\n\nREMINDER: answer ONLY with valid structured output.",
                              stage_models)


# ── node runners ─────────────────────────────────────────────────────────────
async def run_storyteller(*, idx: int, section: dict, prev_heading: str | None,
                          stage_models) -> TakeDraft:
    label = section.get("h2_path") or section.get("section_id") or f"take {idx + 1}"
    user = (f"Previous take heading: {prev_heading or '(this is the first take)'}\n\n"
            f"SECTION: {label}\n\n{section.get('text', '')}")
    try:
        d = await _with_retry("storyteller", TakeDraft, STORYTELLER_PROMPT,
                              user, stage_models)
        d.idx = idx
        return d
    except Exception:  # noqa: BLE001 — degrade, never abort the run
        return TakeDraft(idx=idx, heading=str(label), degraded=True,
                         story=(section.get("text", "") or "")[:1200])


async def run_editor(drafts: list[TakeDraft], stage_models) -> list[TakeDraft]:
    ordered = sorted(drafts, key=lambda d: d.idx)
    user = "\n\n".join(f"[take {d.idx}] {d.heading}\n{d.story}" for d in ordered)
    try:
        out = await _with_retry("editor", TakeDraftList, EDITOR_PROMPT, user, stage_models)
        if len(out.takes) == len(ordered):
            for new, old in zip(out.takes, ordered):
                new.idx, new.key_items, new.degraded = old.idx, old.key_items, old.degraded
            return out.takes
    except Exception:  # noqa: BLE001
        pass
    return ordered  # editor failure → keep drafts


async def run_miner(*, take: TakeDraft, stage_models) -> list[Subject]:
    user = (f"TAKE {take.idx}: {take.heading}\n{take.story}\n"
            f"key_items: {', '.join(take.key_items)}")
    try:
        out = await _with_retry("miner", SubjectList, MINER_PROMPT, user, stage_models)
    except Exception:  # noqa: BLE001
        return []
    for i, s in enumerate(out.subjects[:4]):
        s.take_idx, s.id = take.idx, f"t{take.idx}-s{i}"
    return out.subjects[:4]


async def run_writer(*, take_idx: int, take_heading: str, take_story: str,
                     subjects: list[Subject], evidence: list[Evidence],
                     stage_models) -> list[BulletDraft]:
    ev_block = "\n\n".join(f"[{e.id}] ({e.kind}) {e.text[:1500]}" for e in evidence)
    subj_block = "\n".join(f"- ({s.tag}) {s.title}" for s in subjects)
    user = (f"TAKE: {take_heading}\n{take_story}\n\nSUBJECTS:\n{subj_block}"
            f"\n\nEVIDENCE:\n{ev_block}")
    try:
        out = await _with_retry("writer", WriterOut, WRITER_PROMPT, user, stage_models)
    except Exception:  # noqa: BLE001
        return []
    return [BulletDraft(take_idx=take_idx, subject=b.subject, body=b.body,
                        evidence_ids=b.evidence_ids) for b in out.bullets]


async def run_judge(*, take_heading: str, subjects: list[str],
                    bullets_summary: str, stage_models) -> list[str]:
    user = (f"TAKE: {take_heading}\nSUBJECTS:\n" + "\n".join(f"- {s}" for s in subjects)
            + f"\n\nBULLETS:\n{bullets_summary}")
    try:
        out = await _with_retry("judge", JudgeOut, JUDGE_PROMPT, user, stage_models)
        return [s for s in out.failed_subjects if s in subjects]
    except Exception:  # noqa: BLE001
        return []
