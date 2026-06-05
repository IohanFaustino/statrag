"""Unit tests for per-component equation enforcement on DeepTutorAnswer."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

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


def test_has_real_equation_false_for_text_superscript_word_form():
    body = r"$$\text{Bias}^2 + \text{Variance} \approx \text{MSE}$$"
    assert _has_real_equation(body) is False


def test_has_real_equation_true_for_mathrm_decomposition():
    body = r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$"
    assert _has_real_equation(body) is True


def test_has_real_equation_true_for_plain_variables():
    body = r"$$f(x) = g(x)$$"
    assert _has_real_equation(body) is True


def _answer(definition: str, math_blocks=None) -> dict:
    """Minimal valid DeepTutorAnswer payload with a custom definition."""
    return dict(
        tldr="intro",
        definition=definition,
        formal_statement="",
        example_intuition="ex",
        applications="apps",
        further_reading="more",
        math_blocks=math_blocks or [],
    )


def _build(**kw):
    from src.services.chat.schemas.output import DeepTutorAnswer

    return DeepTutorAnswer(**_answer(**kw))


def test_math_definition_missing_variance_equation_rejected():
    definition = (
        "We define each component.\n"
        "### Bias\n- bias prose\n"
        r"$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$" "\n"
        "### Variance\n- variance prose, but no formula here\n"
        "### MSE\n"
        r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$" "\n"
    )
    with pytest.raises(ValidationError) as exc:
        _build(definition=definition)
    assert "Variance" in str(exc.value)


def test_math_definition_all_subsections_have_equation_valid():
    definition = (
        "We define each component.\n"
        "### Bias\n"
        r"$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$" "\n"
        "### Variance\n"
        r"$$\mathrm{Var}(\hat\theta)=\mathbb{E}[(\hat\theta-\mathbb{E}[\hat\theta])^2]$$" "\n"
        "### MSE\n"
        r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$" "\n"
    )
    ans = _build(definition=definition)
    assert ans.definition == definition


def test_conceptual_definition_no_math_is_exempt():
    definition = (
        "Overfitting is when a model learns noise.\n"
        "### Symptoms\n- high train accuracy, low test accuracy\n"
        "### Causes\n- too much flexibility\n"
    )
    ans = _build(definition=definition)  # no math_blocks, no $$ -> no-op gate
    assert ans.definition == definition


def test_pseudo_equation_rejected():
    definition = (
        "We define each component.\n"
        "### Bias\n"
        r"$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$" "\n"
        "### MSE\n"
        r"$$\text{Squared bias}+\text{Variance}\approx\text{Test MSE}$$" "\n"
    )
    with pytest.raises(ValidationError) as exc:
        _build(definition=definition)
    assert "MSE" in str(exc.value)


def test_header_less_text_definition_does_not_raise():
    # _wrap_text_answer path: raw text, no ### headers -> no-op even if math.
    definition = r"A paragraph mentioning $$x=1$$ with no headers at all."
    ans = _build(definition=definition, math_blocks=[r"$$x=1$$"])
    assert ans.definition == definition
