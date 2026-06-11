from src.services.chat.agents.extension_agents.runner import _isolate_midline_display


def test_isolate_midline_display():
    # mid-line $$ -> $ (would leak raw LaTeX otherwise)
    assert _isolate_midline_display("see $$x^2$$ here") == "see $x^2$ here"
    # a line that wholly owns its $$..$$ block is left intact
    assert _isolate_midline_display("$$x^2$$") == "$$x^2$$"
    # plain text untouched
    assert _isolate_midline_display("no math") == "no math"
