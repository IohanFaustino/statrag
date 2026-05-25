"""Invariant #28 — every prompt constant MUST use the XML schema.

Scans `src/services/chat/prompts/*.py` plus the inline prompt constants in
`src/services/chat/agents/*.py` and asserts that each named PROMPT /
INSTRUCTIONS / PREAMBLE / ADDENDUM / CRITIQUE constant contains
``<role>`` + ``<context>`` + ``<task>`` tags (or the ``_addendum`` variants).
Plain-text prompts are forbidden — they silently break smaller models, as
documented in `docs/common ground/Agents/feature_Agent.md` (Zeroth law).
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3] / "src" / "services" / "chat"

# Triple-quoted top-level constants that look like prompts.
_ASSIGN_RE = re.compile(
    r'^([_A-Z][_A-Z0-9]+)\s*(?::\s*str\s*)?=\s*"""([^"]|"(?!""))*?"""',
    re.M | re.S,
)
_TAG_RE = re.compile(r"<(role|task|context)(?:_addendum)?>", re.I)
_REQUIRED = {"role", "context", "task"}
_PROMPT_NAME_HINTS = ("prompt", "instr", "preamble", "addendum", "critique")


def _prompt_files() -> list[pathlib.Path]:
    files = list((ROOT / "prompts").glob("*.py"))
    files += [
        ROOT / "agents" / "deep_tutor.py",
        ROOT / "agents" / "image_judge.py",
    ]
    return [f for f in files if f.exists()]


def _iter_prompt_constants():
    for f in _prompt_files():
        src = f.read_text()
        for m in _ASSIGN_RE.finditer(src):
            name = m.group(1)
            body = m.group(0)
            if not any(hint in name.lower() for hint in _PROMPT_NAME_HINTS):
                continue
            yield f, name, body


def test_every_prompt_uses_xml_schema() -> None:
    """No prompt constant may ship without role + context + task tags."""
    failures: list[str] = []
    for f, name, body in _iter_prompt_constants():
        tags = {t.lower() for t in _TAG_RE.findall(body)}
        if not _REQUIRED <= tags:
            failures.append(f"{f}::{name} missing={sorted(_REQUIRED - tags)}")
    assert not failures, (
        "Invariant #28 violated — these prompts are not XML-tagged:\n  "
        + "\n  ".join(failures)
    )
