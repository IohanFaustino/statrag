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
