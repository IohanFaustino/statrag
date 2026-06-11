"""Narrative contract tests for the deep-tutor prompt and field descriptions.

Task 3 of the tutor narrative rebuild: verify that field descriptions carry
the beat/bridge contract and that DEEP_TUTOR_INSTRUCTIONS contains a narrative
thread directive. Does NOT test live LLM output.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")
_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.services.chat.schemas.output import DeepTutorAnswer  # noqa: E402
from src.services.chat.prompts import deep_tutor as P  # noqa: E402


def test_field_descriptions_carry_bridge_contract():
    f = DeepTutorAnswer.model_fields
    assert "outside" in f["tldr"].description.lower() or "standalone" in f["tldr"].description.lower()
    for k in ("definition", "example_intuition", "applications", "further_reading"):
        d = f[k].description.lower()
        assert "open" in d and ("previous" in d or "prior" in d)
        assert "next" in d or "set up" in d or "lead" in d


def test_instructions_have_narrative_contract_and_no_orchestrator_tasks():
    txt = P.DEEP_TUTOR_INSTRUCTIONS.lower()
    assert "thread" in txt or "narrative" in txt
    assert "tl;dr" in txt or "introduction" in txt
    assert "tasks" not in P.SYNTHESIS_PLAN_PROMPT.lower() or "worker" not in P.SYNTHESIS_PLAN_PROMPT.lower()
