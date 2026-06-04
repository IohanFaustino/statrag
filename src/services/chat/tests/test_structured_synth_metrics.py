from src.services.chat.eval.structured_synth_compare import (
    count_clean_math_violations, has_component_formulas, count_bullets,
)


def test_clean_math_violations():
    assert count_clean_math_violations("ok $x=1$ and $$y$$") == 0
    assert count_clean_math_violations(r"bad \$(x\)$ here") >= 1


def test_component_formulas():
    good = (
        r"### Bias" "\n"
        r"- **Bias** — $\operatorname{Bias}(\hat f)=E[\hat f]-f$" "\n"
        r"### MSE" "\n"
        r"$$\operatorname{MSE}=b^2+v+\sigma^2$$"
    )
    assert has_component_formulas(good) is True
    assert has_component_formulas("bias is the error and variance is spread") is False


def test_count_bullets():
    assert count_bullets("- **A** — x\n- **B** — y\nplain") == 2
