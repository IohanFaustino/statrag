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
