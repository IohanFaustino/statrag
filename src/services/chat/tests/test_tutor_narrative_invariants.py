from src.services.chat.agents.seams import _first_sentence, _last_sentence
from src.services.chat.schemas.output import DeepTutorAnswer


def test_seam_sentences_never_contain_display_math():
    # guards: transition clauses must not swallow a $$ block onto a seam line
    sample = {
        "definition": "Bias is error. $$\\mathrm{Bias}=\\mathbb{E}[\\hat f]-f$$ It sets up variance.",
        "example_intuition": "Building on bias, variance measures spread. It leads to applications.",
    }
    for k in ("definition", "example_intuition"):
        assert "$$" not in _first_sentence(sample[k])
        assert "$$" not in _last_sentence(sample[k])


def test_component_equation_validator_passes_on_narrative_definition():
    # a math definition whose component subsections each carry a real equation
    ans = DeepTutorAnswer(
        tldr="Intro.",
        definition=(
            "Error decomposes into two components.\n\n"
            "### Bias\nBias is the gap. $$\\mathrm{Bias}=\\mathbb{E}[\\hat f]-f$$\n\n"
            "### Variance\nVariance is the spread. $$\\mathrm{Var}=\\mathbb{E}[(\\hat f-\\mathbb{E}\\hat f)^2]$$"
        ),
        formal_statement="",
        example_intuition="See it on a polynomial fit.",
        applications="Used in random forests.",
        further_reading="See ESL 7.",
        math_blocks=["x"],
    )
    assert ans.definition.count("### ") == 2


def test_component_equation_validator_rejects_wordform_when_other_subsection_is_valid():
    import pytest
    from src.services.chat.schemas.output import DeepTutorAnswer
    with pytest.raises(Exception):
        DeepTutorAnswer(
            tldr="Intro.",
            definition=(
                "Decomposition.\n\n"
                "### Bias\nBias is the gap. $$\\mathrm{Bias}=\\mathbb{E}[\\hat f]-f$$\n\n"
                "### Variance\nWord form only.$$\\text{Variance}\\approx\\text{MSE}$$"
            ),
            formal_statement="",
            example_intuition="x", applications="y", further_reading="z",
            math_blocks=["x"],
        )


def test_component_equation_validator_still_raises_on_wordform():
    import pytest
    with pytest.raises(Exception):
        DeepTutorAnswer(
            tldr="Intro.",
            definition=(
                "Decomposition.\n\n### Bias\nNo formula here, just words about bias.\n\n"
                "### Variance\nAlso words.$$\\text{Variance}\\approx\\text{MSE}$$"
            ),
            formal_statement="",
            example_intuition="x", applications="y", further_reading="z",
            math_blocks=["x"],
        )
