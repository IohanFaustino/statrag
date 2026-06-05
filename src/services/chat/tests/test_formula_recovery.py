import asyncio
import importlib
import src.services.chat.agents.formula_recovery as fr
from src.services.chat.agents.formula_gaps import GapConcept
from src.services.chat.agents.formula_cache import RecoveredEquation
from src.services.chat.schemas import Figure

# Import the inspect_figure *module* (not the re-exported function from tools/__init__.py)
_if_mod = importlib.import_module("src.services.chat.tools.inspect_figure")


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
    async def vis(fig, *, query, **kwargs): return "The equation is $\\text{Bias}=E[\\hat\\theta]-\\theta$ shown above."
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


def test_sibling_gap_isolated_on_failure(monkeypatch):
    # gap A raises in cache_lookup; gap B succeeds via cache. A must not break B.
    async def lookup(term, **k):
        if term == "boom":
            raise RuntimeError("explode")
        return RecoveredEquation(term="ok", latex="$ok$", citation="C")
    monkeypatch.setattr(fr, "cache_lookup", lookup)
    monkeypatch.setattr(fr, "search_figures", lambda *a, **k: [])
    monkeypatch.setattr(fr, "hybrid_search", lambda *a, **k: ([], {}))
    out = asyncio.run(fr.recover_formulas("q", [_gap(term="boom"), _gap(term="ok")]))
    assert len(out) == 1 and out[0].latex == "$ok$"


def test_format_recovered_block():
    block = fr.format_recovered_block([RecoveredEquation(term="Bias", latex="$b$", citation="Murphy")])
    assert "<recovered_equations>" in block and "$b$" in block and "Bias" in block
    assert fr.format_recovered_block([]) == ""


# ---------------------------------------------------------------------------
# inspect_figure: instruction override (Fix 1)
# ---------------------------------------------------------------------------

def _make_fake_openai(captured: dict, response_content: str = "$E[X]$"):
    """Build a minimal fake openai module replacement for monkeypatching."""

    class _FakeChoice:
        message = type("M", (), {"content": response_content})()

    class _FakeUsage:
        prompt_tokens = 10
        completion_tokens = 5

    class _FakeResp:
        choices = [_FakeChoice()]
        usage = _FakeUsage()

    class _FakeCreate:
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            captured["max_tokens"] = kwargs.get("max_tokens")
            return _FakeResp()

    class _FakeCompletions:
        completions = _FakeCreate()

    class _FakeChat:
        completions = _FakeCreate()

    class _FakeOA:
        chat = _FakeChat()

    class _FakeOpenAIModule:
        @staticmethod
        def AsyncOpenAI(**kw):
            return _FakeOA()

    return _FakeOpenAIModule()


def test_inspect_figure_instruction_override_sends_instruction_not_prose(monkeypatch):
    """When instruction= is provided, the OpenAI user text must contain the
    instruction string and must NOT contain the default prose ask."""
    captured = {}
    monkeypatch.setattr(_if_mod, "_openai", _make_fake_openai(captured))
    monkeypatch.setattr(_if_mod, "log_call", lambda **kw: None)

    fig = Figure(ref="r1", book="murphy", chapter="ch04", caption="Bias formula",
                 chart="https://example.com/fig.png")
    custom_instruction = "Transcribe the exact equation as LaTeX. Output ONLY the equation."

    asyncio.run(_if_mod.inspect_figure(
        fig,
        query="bias",
        instruction=custom_instruction,
        max_tokens=200,
    ))

    assert captured, "OpenAI was never called"
    user_text = captured["messages"][0]["content"][0]["text"]
    # instruction must appear in the prompt
    assert custom_instruction in user_text
    # the default prose ask must NOT appear
    assert "In 2-3 sentences" not in user_text
    assert captured["max_tokens"] == 200


def test_inspect_figure_default_path_unchanged(monkeypatch):
    """When instruction is None, the default prose ask must appear verbatim."""
    captured = {}
    monkeypatch.setattr(_if_mod, "_openai", _make_fake_openai(captured, "some prose"))
    monkeypatch.setattr(_if_mod, "log_call", lambda **kw: None)

    fig = Figure(ref="r2", book="islp", chapter="ch03", caption="Figure 3.1",
                 chart="https://example.com/fig2.png")

    asyncio.run(_if_mod.inspect_figure(fig, query="regression line"))

    user_text = captured["messages"][0]["content"][0]["text"]
    assert "In 2-3 sentences" in user_text
    assert "regression line" in user_text
    assert captured["max_tokens"] == 300
