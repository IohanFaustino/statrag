from src.services.chat.agents.seams import check_seams, BEAT_ORDER


def _beats(**kw):
    base = {k: "" for k in BEAT_ORDER}
    base.update(kw)
    return base


def test_connected_beats_pass():
    beats = _beats(
        definition="Test MSE decomposes into bias, variance and noise. This decomposition is the key lever.",
        example_intuition="That decomposition plays out on a polynomial fit. A degree-1 model underfits, lifting bias.",
        applications="The same bias lever governs random forests. Tree depth trades variance for bias in practice.",
        further_reading="Beyond forests, the bias question opens active research. See ESL chapter 7.",
    )
    res = check_seams(beats, thesis="bias and variance trade off to shape test error")
    assert res.passed is True
    assert res.scores["seam_continuity"] == 1.0


def test_disconnected_beat_fails_and_names_seam():
    beats = _beats(
        definition="Test MSE decomposes into bias, variance and noise.",
        example_intuition="Photosynthesis converts sunlight into chemical energy in chloroplasts.",
        applications="The bias lever governs random forests too.",
    )
    res = check_seams(beats, thesis="bias variance tradeoff")
    assert res.passed is False
    assert any("example_intuition" in f for f in res.failing_seams)
    assert res.scores["seam_continuity"] < 1.0


def test_thesis_rescues_a_pivot():
    beats = _beats(
        definition="A model's error has three additive parts.",
        example_intuition="Variance shows up clearly when we refit on resampled data.",
    )
    res = check_seams(beats, thesis="variance drives instability across resamples")
    assert res.passed is True


def test_formalize_drop_relinks_definition_to_example():
    beats = _beats(
        definition="Bias measures how far the average prediction sits from truth.",
        formal_statement="",
        example_intuition="That same bias is visible when a linear fit misses a curved trend.",
        applications="Bias also explains underfitting in shallow trees.",
    )
    res = check_seams(beats, thesis="bias")
    assert res.passed is True


def test_polish_language_drift_flagged():
    beats = _beats(
        definition="Bias mierzy odchylenie predykcji od prawdy w modelu statystycznym.",
        example_intuition="To samo zjawisko widać przy dopasowaniu liniowym do krzywej.",
    )
    res = check_seams(beats, thesis="bias")
    assert res.scores["lang_ok"] == 0.0


def test_boilerplate_openers_flagged():
    beats = _beats(
        definition="Bias is the systematic error of a model. Now that we understand bias, more follows.",
        example_intuition="Now that we understand bias, consider a linear fit to curved data.",
        applications="Now that we understand bias, trees underfit when shallow.",
    )
    res = check_seams(beats, thesis="bias")
    assert res.passed is False
    assert any("boilerplate" in f.lower() for f in res.failing_seams)


def test_figure_reference_does_not_break_seam():
    # a beat ending in an abbreviation ("Fig. 7.") must not split into a
    # digit-only last "sentence" that fails an otherwise-connected seam.
    beats = _beats(
        definition="Bias is the systematic part of prediction error. See Fig. 7.",
        example_intuition="That same bias appears clearly in polynomial underfitting.",
    )
    res = check_seams(beats, thesis="")
    assert res.passed is True
    assert res.scores["seam_continuity"] == 1.0
