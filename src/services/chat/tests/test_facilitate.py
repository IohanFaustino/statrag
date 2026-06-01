from src.services.chat.schemas import (
    ChapterScope, ConceptAnchor, ConceptProvenance, FacilitateBlock, FacilitateDigest,
)


def test_facilitate_schemas_construct():
    prov = ConceptProvenance(book_slug="hansen", authors_short="Hansen",
                             section="7.1 INTRODUCTION", page_from=176, page_to=176,
                             chunk_id="x", same_author=True, fallback=False)
    c = ConceptAnchor(id="c1", term="strong assumption of normality",
                      kind="concept", explanation="Assumes the data are normal.",
                      provenance=prov)
    blk = FacilitateBlock(h2_path="7.1 INTRODUCTION", section_id="x",
                          key_points=["a", "b"], body="text [[c1]]", concepts=[c],
                          page_from=176, page_to=176)
    scope = ChapterScope(book_slug="hansen", chapter_id="ch07", requested_subtopics=[])
    dig = FacilitateDigest(mode="facilitate", scope=scope, blocks=[blk])
    assert dig.blocks[0].concepts[0].kind == "concept"
    assert dig.blocks[0].key_points == ["a", "b"]
    assert dig.mode == "facilitate"
