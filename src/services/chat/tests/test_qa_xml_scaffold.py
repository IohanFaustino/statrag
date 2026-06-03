"""QA prompts use the <role>/<task>/<output_format>/<rules> scaffold."""
from __future__ import annotations

import pytest

from src.services.chat.prompts import qa

PROMPTS = ["QA_SCOPE_PROMPT", "QA_GENERATE_PROMPT", "QA_VERIFY_PROMPT"]
TAGS = ["role", "task", "output_format", "rules"]


@pytest.mark.parametrize("name", PROMPTS)
def test_prompt_opens_with_role(name):
    text = getattr(qa, name)
    assert text.lstrip().startswith("<role>"), f"{name}: must open with <role>"


@pytest.mark.parametrize("name", PROMPTS)
@pytest.mark.parametrize("tag", TAGS)
def test_prompt_has_all_scaffold_tags(name, tag):
    text = getattr(qa, name)
    assert f"<{tag}>" in text and f"</{tag}>" in text, (
        f"{name}: missing <{tag}>...</{tag}>"
    )


@pytest.mark.parametrize("name", PROMPTS)
def test_json_instruction_lives_inside_output_format(name):
    text = getattr(qa, name)
    if "Return ONLY a JSON object" not in text:
        return
    before = text.split("<output_format>", 1)[0]
    assert "Return ONLY a JSON object" not in before, (
        f"{name}: JSON instruction leaked outside <output_format>"
    )
