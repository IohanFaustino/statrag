from src.services.chat.schemas import ExtensionPoint, ExtensionFootnote
from src.services.chat.agents.extension_agents.runner import curated_text_is_clean


def test_curated_text_has_no_augmentation_markers():
    good = ExtensionPoint(title="t", curated_text="The mean converges.",
                          footnotes=[ExtensionFootnote(marker="1", body="$x$",
                                                       source="ross §1", kind="corpus")])
    assert curated_text_is_clean(good) is True
    bad = ExtensionPoint(title="t",
                         curated_text="See https://en.wikipedia.org/wiki/X for more.",
                         footnotes=[])
    assert curated_text_is_clean(bad) is False


def test_isolate_midline_display():
    from src.services.chat.agents.extension_agents.runner import _isolate_midline_display
    # mid-line $$ -> $ (would leak raw LaTeX otherwise)
    assert _isolate_midline_display("see $$x^2$$ here") == "see $x^2$ here"
    # a line that wholly owns its $$..$$ block is left intact
    assert _isolate_midline_display("$$x^2$$") == "$$x^2$$"
    # plain text untouched
    assert _isolate_midline_display("no math") == "no math"
