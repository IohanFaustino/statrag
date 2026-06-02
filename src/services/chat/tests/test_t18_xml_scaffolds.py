"""T18 acceptance: XML-scaffolded mode prompts."""
from __future__ import annotations

import importlib

import pytest


def _load(mode: str) -> str:
    mod = importlib.import_module(f"src.services.chat.prompts.{mode}")
    return getattr(mod, "TUTOR_INSTRUCTIONS", None) or getattr(mod, "INSTRUCTIONS")


@pytest.mark.parametrize("mode", ["tutor"])
def test_prompt_has_xml_scaffold_role(mode):
    """T18: tutor prompt opens with a <role> tag."""
    text = _load(mode)
    assert "<role>" in text and "</role>" in text, (
        f"{mode}: missing <role>...</role> scaffold"
    )


@pytest.mark.parametrize("mode", ["tutor"])
def test_prompt_has_xml_scaffold_task(mode):
    text = _load(mode)
    assert "<task>" in text and "</task>" in text, (
        f"{mode}: missing <task>...</task> scaffold"
    )


@pytest.mark.parametrize("mode", ["tutor"])
def test_prompt_has_xml_scaffold_output_format(mode):
    text = _load(mode)
    assert "<output_format>" in text and "</output_format>" in text, (
        f"{mode}: missing <output_format>...</output_format>"
    )


@pytest.mark.parametrize("mode", ["tutor"])
def test_prompt_has_xml_scaffold_rules(mode):
    text = _load(mode)
    assert "<rules>" in text and "</rules>" in text, (
        f"{mode}: missing <rules>...</rules>"
    )


def test_live_modes_have_failure_mode_section():
    """Tutor prompt declares a <failure_mode> branch."""
    text = _load("tutor")
    assert "<failure_mode>" in text and "</failure_mode>" in text, (
        "tutor: missing <failure_mode>...</failure_mode>"
    )


def test_tutor_has_citation_template():
    text = _load("tutor")
    assert "<citation_template>" in text
    assert "{authors_short}" in text
    assert "{year}" in text
    assert "{page_from}" in text


def test_tutor_has_example_block():
    """T18: at least one <example> guides format adherence."""
    text = _load("tutor")
    assert "<example>" in text and "</example>" in text


def test_tutor_no_legacy_hard_rules_marker():
    """Old `HARD RULES:` numbered list should not coexist with the XML scaffold."""
    text = _load("tutor")
    assert "HARD RULES" not in text, "legacy 'HARD RULES:' marker still present"


def test_no_apa_unknown_fallback_in_tutor():
    """T18 + T13: tutor prompt forbids 'Unknown' / 'None' fallback strings."""
    import re

    text = _load("tutor")
    if "Unknown" in text:
        flat = re.sub(r"\s+", " ", text)
        assert "never print" in flat or "no \"Unknown\"" in flat, (
            "'Unknown' appears outside the explicit-prohibition clause"
        )


@pytest.mark.parametrize("mode", ["tutor"])
def test_no_outdated_numbered_hard_rules(mode):
    """Tutor prompt dropped the v1 'HARD RULES: 1. ... 7. ...' block."""
    text = _load(mode)
    assert "HARD RULES" not in text, f"{mode}: v1 'HARD RULES:' marker still present"


_FACILITATE_PROMPTS = [
    "FACILITATE_MAP_PROMPT",
    "FACILITATE_INTRO_PROMPT",
    "FACILITATE_EXPLAIN_PROMPT",
    "FACILITATE_TEACH_PROMPT",
    "FACILITATE_VERIFY_PROMPT",
]


@pytest.mark.parametrize("name", _FACILITATE_PROMPTS)
def test_facilitate_prompt_has_xml_scaffold(name):
    """Facilitate prompts use the <role>/<task>/<output_format> XML scaffold,
    not the legacy 'ROLE:'/'TASK:'/'OUTPUT FORMAT:' label pattern."""
    mod = importlib.import_module("src.services.chat.prompts.chapter")
    text = getattr(mod, name)
    assert "<role>" in text and "</role>" in text, f"{name}: missing <role> scaffold"
    assert "<task>" in text and "</task>" in text, f"{name}: missing <task> scaffold"
    assert "<output_format>" in text and "</output_format>" in text, (
        f"{name}: missing <output_format> scaffold"
    )
    for legacy in ("ROLE:", "TASK:", "OUTPUT FORMAT"):
        assert legacy not in text, f"{name}: legacy '{legacy}' label still present"
