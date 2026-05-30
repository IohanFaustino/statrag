# code:neo4j_llm:ch06 — Exploring Advanced Knowledge Graph Capabilities with Neo4j

book: Building Neo4j-Powered Applications with LLMs
slug: neo4j_llm
chapter: ch06
chapter_title: Exploring Advanced Knowledge Graph Capabilities with Neo4j
repo: https://github.com/PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs (branch main)
folder: ch6

## Summary
Chapter 6 extends the Haystack + Neo4j integration with advanced graph reasoning patterns. `beyond_basic_search.py` adds multi-hop traversal (director → related movies), dynamic property filtering, and optimised top-k tuning on top of the existing vector index. `graph_reasoning.py` demonstrates traversal through both ACTED_IN and DIRECTED relationships simultaneously to surface hidden connections, then combines the graph-retrieved documents with vector similarity search using pre-stored embeddings.

## Libraries & frameworks
dotenv, haystack, neo4j, neo4j_haystack, openai, os

## Models & APIs
- `text-embedding-ada-002` (OpenAI, 1536-dim, via `OpenAITextEmbedder`)
- Neo4j vector index `overview_embeddings` (cosine, 1536-dim)
- `Neo4jDocumentStore`, `Neo4jEmbeddingRetriever` from `neo4j_haystack`

## Concepts / patterns
- multi-hop graph traversal in Cypher (Director → related Movie nodes)
- graph + vector hybrid retrieval: graph traversal narrows candidate set, then vector search re-ranks
- dynamic property filtering in Haystack pipeline (`filters`: release_date ≥ threshold)
- optimised top-k retrieval with `query_by_embedding`
- role-aware multi-hop reasoning (Actor vs Director role detection via CASE expression)

## Files
- beyond_basic_search.py — Multi-hop semantic search: traverses director relationships to fetch related movies, then re-ranks with `text-embedding-ada-002`; also demonstrates filtered and optimised search (py)
- graph_reasoning.py — Traverses ACTED_IN and DIRECTED relationships simultaneously to identify shared actors/directors, writes results to document store, and re-ranks with vector similarity (py)

## Code entities
- beyond_basic_search.py: fetch_multi_hop_related_movies, perform_semantic_search_with_multi_hop, perform_filtered_search, perform_optimized_search, main
- graph_reasoning.py: fetch_multi_hop_related_movies, fetch_related_movies_via_actors_and_directors, main

## Key snippets

```cypher
-- beyond_basic_search.py — multi-hop: director → related movies
MATCH (m:Movie {title: $title})<-[:DIRECTED]-(d:Director)-[:DIRECTED]->(related:Movie)
RETURN related.title AS related_movie, related.overview AS overview
```

```cypher
-- graph_reasoning.py — multi-hop via actors AND directors with role detection
MATCH (m:Movie {title: $title})<-[:ACTED_IN|DIRECTED]-(p)-[:ACTED_IN|DIRECTED]->(related:Movie)
WITH related.title AS related_movie, p.name AS person,
     CASE
        WHEN (p)-[:ACTED_IN]->(m) AND (p)-[:ACTED_IN]->(related) THEN 'Actor'
        WHEN (p)-[:DIRECTED]->(m) AND (p)-[:DIRECTED]->(related) THEN 'Director'
        ELSE 'Unknown Role'
     END AS role,
     related.overview AS overview
RETURN related_movie, person, role, overview
```

```python
# beyond_basic_search.py — filtered Haystack pipeline search
result = pipeline.run(data={
    "query_embedder": {"text": query},
    "retriever": {
        "top_k": 5,
        "filters": {"field": "release_date", "operator": ">=", "value": "1995-11-17"},
    },
})
```
