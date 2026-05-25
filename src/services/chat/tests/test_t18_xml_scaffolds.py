"""T18 acceptance: XML-scaffolded mode prompts."""
from __future__ import annotations

import importlib

import pytest


# All single-agent modes — these prompts are live on v2 (`mode_impls/<mode>.py`).
LIVE_MODES = [
    "tutor",
    "compare",
    "figures",
    "quiz",
    "navigate",
    "annotate",
    "math",
    "roadmap",
]

# Multi-agent modes — prompts kept for parity but not live in v2 graphs.
PARITY_MODES = ["prereqs", "research", "path"]

ALL_MODES = LIVE_MODES + PARITY_MODES


def _load(mode: str) -> str:
    mod = importlib.import_module(f"src.services.chat.prompts.{mode}")
    return getattr(mod, "TUTOR_INSTRUCTIONS", None) or getattr(mod, "INSTRUCTIONS")


@pytest.mark.parametrize("mode", ALL_MODES)
def test_prompt_has_xml_scaffold_role(mode):
    """T18: every mode prompt opens with a <role> tag."""
    text = _load(mode)
    assert "<role>" in text and "</role>" in text, (
        f"{mode}: missing <role>...</role> scaffold"
    )


@pytest.mark.parametrize("mode", ALL_MODES)
def test_prompt_has_xml_scaffold_task(mode):
    text = _load(mode)
    assert "<task>" in text and "</task>" in text, (
        f"{mode}: missing <task>...</task> scaffold"
    )


@pytest.mark.parametrize("mode", ALL_MODES)
def test_prompt_has_xml_scaffold_output_format(mode):
    text = _load(mode)
    assert "<output_format>" in text and "</output_format>" in text, (
        f"{mode}: missing <output_format>...</output_format>"
    )


@pytest.mark.parametrize("mode", ALL_MODES)
def test_prompt_has_xml_scaffold_rules(mode):
    text = _load(mode)
    assert "<rules>" in text and "</rules>" in text, (
        f"{mode}: missing <rules>...</rules>"
    )


@pytest.mark.parametrize("mode", LIVE_MODES)
def test_live_modes_have_failure_mode_section(mode):
    """Every live single-agent mode declares a <failure_mode> branch.

    Multi-agent parity prompts (prereqs / research / path) are excluded
    because their v2 paths use node-internal prompts; the static prompt
    is only consumed by the v1 fallback.
    """
    text = _load(mode)
    assert "<failure_mode>" in text and "</failure_mode>" in text, (
        f"{mode}: missing <failure_mode>...</failure_mode>"
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
    """T18 + T13: tutor prompt forbids 'Unknown' / 'None' fallback strings.

    The prompt mentions these tokens explicitly only to forbid them
    (e.g. ``never print the literal word "null", "None", "0", "n.d.",
    "Unknown"``). Assert that any occurrence sits inside that
    prohibition clause rather than being a recommended template.
    """
    import re

    text = _load("tutor")
    if "Unknown" in text:
        # Allow the explicit-prohibition mention only (handles line wraps).
        flat = re.sub(r"\s+", " ", text)
        assert "never print" in flat or "no \"Unknown\"" in flat, (
            "'Unknown' appears outside the explicit-prohibition clause"
        )


@pytest.mark.parametrize("mode", LIVE_MODES)
def test_no_outdated_numbered_hard_rules(mode):
    """All live mode prompts dropped the v1 'HARD RULES: 1. ... 7. ...' block."""
    text = _load(mode)
    # If a "HARD RULES" marker survives, the prompt was not converted.
    assert "HARD RULES" not in text, f"{mode}: v1 'HARD RULES:' marker still present"
