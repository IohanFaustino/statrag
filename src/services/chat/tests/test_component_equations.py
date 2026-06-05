"""Unit tests for per-component equation enforcement on DeepTutorAnswer."""
from __future__ import annotations

import pytest  # noqa: F401
from pydantic import ValidationError  # noqa: F401

from src.services.chat.schemas.output import (
    _has_real_equation,
    _split_definition_subsections,
)


def test_split_definition_subsections_returns_name_and_body():
    text = (
        "framing sentence with no header.\n"
        "### Bias\nbias prose\n"
        "### Variance\nvariance prose\n"
    )
    subs = _split_definition_subsections(text)
    assert [name for name, _ in subs] == ["Bias", "Variance"]
    assert "bias prose" in dict(subs)["Bias"]


def test_split_definition_subsections_empty_when_no_headers():
    assert _split_definition_subsections("just a paragraph, no headers") == []


def test_has_real_equation_true_for_symbolic_block():
    body = r"text before $$\mathrm{Var}(\hat\theta)=\mathbb{E}[(\hat\theta-\mathbb{E}[\hat\theta])^2]$$ after"
    assert _has_real_equation(body) is True


def test_has_real_equation_false_when_no_block():
    assert _has_real_equation("only prose, no dollars") is False


def test_has_real_equation_false_for_word_form_pseudo_equation():
    body = r"$$\text{Squared bias}+\text{Variance}\approx\text{Test MSE}$$"
    assert _has_real_equation(body) is False
