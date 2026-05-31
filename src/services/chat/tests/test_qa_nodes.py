"""Q&A node + prompt tests."""
from __future__ import annotations


def test_prompts_present_and_nonempty():
    from src.services.chat.prompts.qa import (
        QA_SCOPE_PROMPT,
        QA_GENERATE_PROMPT,
        QA_VERIFY_PROMPT,
    )
    for p in (QA_SCOPE_PROMPT, QA_GENERATE_PROMPT, QA_VERIFY_PROMPT):
        assert isinstance(p, str) and len(p) > 50


def test_scope_prompt_demands_json_keys():
    from src.services.chat.prompts.qa import QA_SCOPE_PROMPT
    for key in ("target_gap", "assumed_known", "answer_form"):
        assert key in QA_SCOPE_PROMPT


def test_generate_prompt_forbids_explaining_known():
    from src.services.chat.prompts.qa import QA_GENERATE_PROMPT
    low = QA_GENERATE_PROMPT.lower()
    assert "assumed_known" in low or "already know" in low
