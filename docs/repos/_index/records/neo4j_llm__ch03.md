# code:neo4j_llm:ch03 — Building a Foundational Understanding of Knowledge Graph for Intelligent Applications

book: Building Neo4j-Powered Applications with LLMs
slug: neo4j_llm
chapter: ch03
chapter_title: Building a Foundational Understanding of Knowledge Graph for Intelligent Applications
repo: https://github.com/PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs (branch main)
folder: ch3

## Summary
Chapter 3 introduces Neo4j as a knowledge graph backend with three progressive examples using the `neo4j` Python driver. The code constructs a simple IMDB-style movie knowledge graph (Movie → Plot nodes with HAS_PLOT relationships), applies Graph Data Science (GDS) PageRank to score movie importance, and demonstrates a RAG pipeline that fetches graph-stored plots and generates answers with the HuggingFace `facebook/rag-token-base` model.

## Libraries & frameworks
neo4j, transformers

## Models & APIs
- Neo4j (local bolt connection)
- Neo4j Graph Data Science (GDS) — `gds.graph.project`, `gds.pageRank.stream`
- `facebook/rag-token-base` (RagTokenForGeneration + RagRetriever + RagTokenizer)

## Concepts / patterns
- knowledge graph construction in Neo4j (Movie, Plot nodes; HAS_PLOT relationships)
- Cypher MERGE/MATCH queries for graph CRUD
- Graph Data Science (GDS) graph projection and PageRank algorithm
- GraphRAG: Cypher retrieval from Neo4j feeding a HuggingFace RAG model
- retrieve-then-generate pattern using graph-stored context

## Files
- imdb_kg.py — Constructs a movie knowledge graph in Neo4j with Movie and Plot nodes linked by HAS_PLOT, then queries it (py)
- neo4j_gds.py — Projects the graph into GDS memory, runs PageRank on movies, then drops the projection (py)
- neo4j_rag.py — GraphRAG: retrieves movie plots from Neo4j via Cypher and generates answers with `facebook/rag-token-base` (py)

## Code entities
- imdb_kg.py: create_graph, query_graph
- neo4j_gds.py: project_graph, run_pagerank, drop_graph, add_relationship_weights
- neo4j_rag.py: get_relevant_data, generate_response

## Key snippets

```cypher
// imdb_kg.py — create Movie-Plot relationship
MATCH (m:Movie {title: 'The Matrix'}),
      (p:Plot {description: '...'})
CREATE (m)-[:HAS_PLOT]->(p)
```

```python
# neo4j_gds.py — PageRank on movie graph
def run_pagerank():
    query = """
    CALL gds.pageRank.stream('movieGraph')
    YIELD nodeId, score
    RETURN gds.util.asNode(nodeId).title AS movie, score
    ORDER BY score DESC;
    """
```

```python
# neo4j_rag.py — GraphRAG retrieve + generate
def get_relevant_data(prompt):
    query = f"""
    MATCH (m:Movie)-[:HAS_PLOT]->(p:Plot)
    WHERE m.title CONTAINS '{prompt}'
    RETURN m.title AS title, m.year AS year, p.description AS plot
    """
    ...

def generate_response(prompt):
    relevant_data = get_relevant_data(prompt)
    combined_input = f"Provide detailed information about: {prompt}. " + ...
    outputs = model.generate(**tokenized_input, max_length=150, num_beams=5)
```
