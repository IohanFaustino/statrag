"""Tests for Q&A storytelling prompts.

Asserts structural invariants for the four prompt constants in
src.services.chat.prompts.qa:

- QA_SCOPE_PROMPT        — scope extraction, now includes wiki_terms
- QA_STORY_WRITE_PROMPT  — storytelling writer; emits [[eid]] tokens
- QA_VERIFY_PROMPT       — advisory grounding audit (no prose rewrite)
- QA_FALLBACK_PROMPT     — corpus-only deterministic generate (no [[eid]])

All are pure string constants; no src.* imports in the prompt module.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load():
    from src.services.chat.prompts import qa
    return qa


# ---------------------------------------------------------------------------
# 1. All four constants exist
# ---------------------------------------------------------------------------

def test_all_constants_exist():
    qa = _load()
    for name in (
        "QA_SCOPE_PROMPT",
        "QA_STORY_WRITE_PROMPT",
        "QA_VERIFY_PROMPT",
        "QA_FALLBACK_PROMPT",
    ):
        assert hasattr(qa, name), f"Missing constant: {name}"


# ---------------------------------------------------------------------------
# 2. Every constant contains <task> / </task>
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "QA_SCOPE_PROMPT",
    "QA_STORY_WRITE_PROMPT",
    "QA_VERIFY_PROMPT",
    "QA_FALLBACK_PROMPT",
])
def test_constant_has_task_tag(name):
    qa = _load()
    text = getattr(qa, name)
    assert "<task>" in text, f"{name} missing <task>"
    assert "</task>" in text, f"{name} missing </task>"


# ---------------------------------------------------------------------------
# 3. QA_SCOPE_PROMPT mentions wiki_terms
# ---------------------------------------------------------------------------

def test_scope_prompt_mentions_wiki_terms():
    qa = _load()
    assert "wiki_terms" in qa.QA_SCOPE_PROMPT


# ---------------------------------------------------------------------------
# 4. QA_STORY_WRITE_PROMPT — [[eid]], arc, forbids headings
# ---------------------------------------------------------------------------

def test_story_write_prompt_mentions_eid_token():
    qa = _load()
    assert "[[" in qa.QA_STORY_WRITE_PROMPT


def test_story_write_prompt_mentions_arc_sections():
    qa = _load()
    text = qa.QA_STORY_WRITE_PROMPT
    assert "intro" in text
    assert "deepening" in text
    assert "conclusion" in text


def test_story_write_prompt_mentions_story_or_narrative():
    qa = _load()
    text = qa.QA_STORY_WRITE_PROMPT.lower()
    assert "story" in text or "narrative" in text


def test_story_write_prompt_forbids_headings():
    qa = _load()
    # Must mention "heading" in its rules so the LLM knows to avoid them
    assert "heading" in qa.QA_STORY_WRITE_PROMPT.lower()


# ---------------------------------------------------------------------------
# 5. QA_FALLBACK_PROMPT — mentions arc sections; no dangling [n] instruction
# ---------------------------------------------------------------------------

def test_fallback_prompt_mentions_arc_sections():
    qa = _load()
    text = qa.QA_FALLBACK_PROMPT
    assert "intro" in text
    assert "deepening" in text
    assert "conclusion" in text


def test_fallback_prompt_does_not_instruct_inline_n_markers():
    """The fallback path skips citation binding (citations=[]).
    Instructing the LLM to emit [n] markers would produce dangling text.
    The prompt must NOT contain that instruction.
    """
    qa = _load()
    text = qa.QA_FALLBACK_PROMPT.lower()
    # The old offending phrase was "use inline [n] markers to cite source numbers"
    assert "use inline [n]" not in text, (
        "QA_FALLBACK_PROMPT must not instruct emitting [n] markers — "
        "the fallback path skips citation binding and [n] would dangle."
    )
    assert "cite source numbers" not in text, (
        "QA_FALLBACK_PROMPT must not instruct numbered citation markers."
    )
