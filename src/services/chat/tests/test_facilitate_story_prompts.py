# src/services/chat/tests/test_facilitate_story_prompts.py
from src.services.chat.prompts.chapter import (
    FACILITATE_STORY_WRITE_PROMPT, FACILITATE_BRIEF_PROMPT,
)


def test_write_prompt_demands_verbatim_formal_and_arc():
    p = FACILITATE_STORY_WRITE_PROMPT.lower()
    assert "verbatim" in p
    assert "hook" in p and "movements" in p and "takeaway" in p
    assert "[[c" in FACILITATE_STORY_WRITE_PROMPT  # concept-anchor instruction
    for w in ("elements", "associations", "intuition"):
        assert w in p


def test_brief_prompt_is_short_and_grounded():
    p = FACILITATE_BRIEF_PROMPT.lower()
    assert "two sentence" in p or "2 sentence" in p or "≤2" in p or "two-sentence" in p
    assert "wikipedia" in p or "passage" in p or "evidence" in p
