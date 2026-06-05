from src.services.chat.agents.formula_gaps import detect_formula_gaps, GapConcept


def _src(chunk, book="murphy", section="4.7"):
    from src.services.chat.schemas import Source
    return Source(rank=1, book=book, chapter="ch04", section=section, title="t",
                  excerpt=chunk[:120], chunkId="c1", chunk=chunk, score=0.9)


def test_gap_when_definition_has_image_placeholder_and_no_latex():
    chunk = ("The bias of an estimator is defined as\n\n"
             "![art](markdown/media/Art_P760.jpg)\n\n"
             "where theta* is the true parameter value.")
    gaps = detect_formula_gaps([_src(chunk)], "bias variance tradeoff")
    assert len(gaps) == 1
    assert "bias" in gaps[0].term.lower()
    assert gaps[0].book_slugs == ["murphy"]


def test_no_gap_when_latex_present_near_definition():
    chunk = ("The estimator is unbiased if and only if $E(\\widehat{\\mu}) = \\mu$ "
             "which is the defining condition.")
    gaps = detect_formula_gaps([_src(chunk, book="baltagi")], "bias")
    assert gaps == []


def test_dedupe_same_term_across_chunks():
    chunk = ("Bias of an estimator is defined as\n![art](a.jpg)\nwhere x.")
    gaps = detect_formula_gaps([_src(chunk), _src(chunk, book="islp")], "bias")
    assert len(gaps) == 1
    assert set(gaps[0].book_slugs) == {"murphy", "islp"}


def test_cap_at_four_gaps():
    srcs = []
    for i, term in enumerate(["bias", "variance", "mse", "consistency", "efficiency"]):
        c = f"The {term} of an estimator is defined as\n![art](x{i}.jpg)\nwhere y."
        srcs.append(_src(c, book=f"b{i}", section=str(i)))
    gaps = detect_formula_gaps(srcs, "estimator properties")
    assert len(gaps) <= 4
