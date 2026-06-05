import asyncio
import src.services.chat.agents.formula_recovery as fr
from src.services.chat.agents.formula_gaps import GapConcept
from src.services.chat.agents.formula_cache import RecoveredEquation


def _gap(term="bias", books=("murphy",)):
    return GapConcept(term=term, hint="bias is defined as", book_slugs=list(books))


def test_cache_hit_short_circuits_vision(monkeypatch):
    async def hit(term, **k): return RecoveredEquation(term="bias", latex="$cached$", citation="C")
    monkeypatch.setattr(fr, "cache_lookup", hit)
    called = {"vision": False}
    def figs(*a, **k): called["vision"] = True; return []
    monkeypatch.setattr(fr, "search_figures", figs)
    out = asyncio.run(fr.recover_formulas("q", [_gap()]))
    assert out and out[0].latex == "$cached$" and called["vision"] is False


def test_vision_path_extracts_latex(monkeypatch):
    async def miss(term, **k): return None
    monkeypatch.setattr(fr, "cache_lookup", miss)
    async def noop_write(*a, **k): return None
    monkeypatch.setattr(fr, "cache_write", noop_write)
    class _Fig: chart="http://x/a.jpg"; caption="Bias"; book="murphy"; chapter="ch04"; ref="r"
    monkeypatch.setattr(fr, "search_figures", lambda *a, **k: [_Fig()])
    async def vis(fig, *, query): return "The equation is $\\text{Bias}=E[\\hat\\theta]-\\theta$ shown above."
    monkeypatch.setattr(fr, "inspect_figure", vis)
    out = asyncio.run(fr.recover_formulas("q", [_gap()]))
    assert out and out[0].latex == "$\\text{Bias}=E[\\hat\\theta]-\\theta$"


def test_text_fallback_when_no_figure(monkeypatch):
    async def miss(term, **k): return None
    monkeypatch.setattr(fr, "cache_lookup", miss)
    async def noop_write(*a, **k): return None
    monkeypatch.setattr(fr, "cache_write", noop_write)
    monkeypatch.setattr(fr, "search_figures", lambda *a, **k: [])
    class _S: chunk = "bias is defined as $E[\\hat\\theta]-\\theta$ in the text"
    monkeypatch.setattr(fr, "hybrid_search", lambda *a, **k: ([_S()], {}))
    out = asyncio.run(fr.recover_formulas("q", [_gap()]))
    assert out and "E[\\hat\\theta]" in out[0].latex


def test_total_miss_yields_no_equation(monkeypatch):
    async def miss(term, **k): return None
    monkeypatch.setattr(fr, "cache_lookup", miss)
    monkeypatch.setattr(fr, "search_figures", lambda *a, **k: [])
    monkeypatch.setattr(fr, "hybrid_search", lambda *a, **k: ([], {}))
    out = asyncio.run(fr.recover_formulas("q", [_gap()]))
    assert out == []


def test_format_recovered_block():
    block = fr.format_recovered_block([RecoveredEquation(term="Bias", latex="$b$", citation="Murphy")])
    assert "<recovered_equations>" in block and "$b$" in block and "Bias" in block
    assert fr.format_recovered_block([]) == ""
