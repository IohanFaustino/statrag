# Retrieval Service

Hybrid query (dense + sparse + RRF fusion) over text collections, plus separate caption-only search over image collections.

## Where things live

| What | Path |
|---|---|
| Retrievers (text + image) | `src/services/retrieval/retrievers.py` |
| LCEL chain (retrieval + LLM answer) | `src/services/retrieval/chain.py` |
| CLI entry | `src/services/retrieval/cli.py` |
| Shared Qdrant helpers | `src/core/qdrant_store.py` |
| Shared config | `src/core/config.py` |


## Quick query

| Action | How |
|---|---|
| Text RAG query | `docs/docs/notebooks/00_run_all.ipynb` cell 7, or `python -m src.services.retrieval.cli "<q>" --book <slug>` |
| Image search | Notebook cell 8, or `--search-images` flag |
| Filter by `field` (collection) | Default — collection name `= <field>_textbooks` |
| Filter by `theme` (within collection) | `Filter(must=[FieldCondition(key="theme", match=MatchValue(value="Machine Learning"))])` |
| Filter by `book` | Same, key=`book`, value=slug |
| Visual DB inspection | `http://localhost:6333/dashboard` |
| Compare LLM providers | `docs/notebooks/04_compare_providers.ipynb` |

## Hybrid retrieval mechanics

For deep mechanics (LCEL composition, RRF, prompt templates, top_k, reranker plan), see [`../guides/specialist.md`](../guides/specialist.md).

For the intuition (why hybrid, why RRF), see [`../guides/medium.md`](../guides/medium.md).

## Cross-field queries (future)

Right now retrieval is bound to a single collection via `settings.qdrant_collection_text`. Querying across fields (e.g. ask "X" against both `introduction_textbooks` and `econometrics_textbooks`) requires:

1. Iterate fields, query each collection.
2. Merge results with RRF.
3. Apply theme/book filters per-collection if relevant.

Tracked under upcoming services — see [`../../docs/upgrades/abstract.md`](../../docs/upgrades/abstract.md) §2 (Cross-Book Comparison Mode).

## Reranker (planned)

Cohere `rerank-3` or `bge-reranker-v2-m3` after RRF fusion. Not implemented. See open work in [`../system/changelog.md`](../system/changelog.md).
