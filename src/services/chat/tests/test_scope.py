from src.services.chat.books import parse_catalog
from src.services.chat.schemas import CatalogBook


def test_parse_catalog_returns_books_with_chapters():
    cat = parse_catalog()
    assert isinstance(cat, list)
    assert cat and all(isinstance(b, CatalogBook) for b in cat)
    b = cat[0]
    assert b.slug and b.name
    assert all(c.startswith("ch") for c in b.chapters)
    assert b.chapters == sorted(b.chapters)


from src.services.chat.agents._scope import expand_section_refs


def test_expand_section_refs_range():
    assert expand_section_refs("sections 7.2 up to 7.4") == ["7.2", "7.3", "7.4"]

def test_expand_section_refs_list_and_dash():
    assert expand_section_refs("7.2, 7.3 and 7.5") == ["7.2", "7.3", "7.5"]
    assert expand_section_refs("7.2-7.4") == ["7.2", "7.3", "7.4"]

def test_expand_section_refs_none():
    assert expand_section_refs("teach me about variance") == []
