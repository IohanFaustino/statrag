# code:neo4j_llm:ch05 — Implementing Powerful Search Functionalities with Neo4j and Haystack

book: Building Neo4j-Powered Applications with LLMs
slug: neo4j_llm
chapter: ch05
chapter_title: Implementing Powerful Search Functionalities with Neo4j and Haystack
repo: https://github.com/PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs (branch main)
folder: ch5

## Summary
Chapter 5 integrates Haystack 2.x with Neo4j to enable vector similarity search over movie overviews using the OpenAI `text-embedding-ada-002` model. Embeddings are generated with parallelised `ThreadPoolExecutor` calls and stored directly on Movie nodes in Neo4j. Two search approaches are demonstrated: direct `Neo4jDocumentStore.query_by_embedding` and a Cypher-powered `db.index.vector.queryNodes` pipeline via `Neo4jDynamicDocumentRetriever`. A Gradio chatbot UI wraps the Cypher pipeline to create an interactive movie recommendation system.

## Libraries & frameworks
concurrent, dotenv, gradio, haystack, neo4j, neo4j_haystack, numpy, openai, os, warnings

## Models & APIs
- `text-embedding-ada-002` (OpenAI, 1536-dim, via `haystack.components.embedders.OpenAITextEmbedder`)
- Neo4j vector index (`overview_embeddings`, cosine similarity, 1536-dim)
- Neo4j Aura (or local Neo4j via bolt)

## Concepts / patterns
- vector index in Neo4j (`CREATE VECTOR INDEX … FOR (m:Movie) ON (m.embedding)`)
- graph + vector hybrid retrieval using Cypher `db.index.vector.queryNodes`
- Haystack 2.x pipeline composition (`Pipeline.add_component`, `Pipeline.connect`)
- `Neo4jDocumentStore` and `Neo4jDynamicDocumentRetriever` from `neo4j_haystack`
- parallel embedding generation with `ThreadPoolExecutor`
- Gradio chat UI for interactive semantic movie recommendations

## Files
- generate_embeddings.py — Generates `text-embedding-ada-002` embeddings for movie overviews in parallel (ThreadPoolExecutor) and stores them on Movie nodes in Neo4j (py)
- search_chatbot.py — Gradio chatbot that embeds user queries and retrieves matching movies via a Haystack pipeline using `db.index.vector.queryNodes` Cypher (py)
- vector_search.py — Demonstrates both direct Haystack `Neo4jDocumentStore` vector search and Cypher-powered `Neo4jDynamicDocumentRetriever` pipeline search (py)

## Code entities
- generate_embeddings.py: initialize_haystack, retrieve_movie_plots, store_embedding_in_neo4j, generate_and_store_embeddings, verify_embeddings, main
- search_chatbot.py: create_or_reset_vector_index, perform_vector_search_cypher, chatbot, main
- vector_search.py: create_or_reset_vector_index, perform_vector_search, perform_vector_search_cypher, main

## Key snippets

```cypher
-- Create vector index on Movie.embedding
CREATE VECTOR INDEX overview_embeddings IF NOT EXISTS
FOR (m:Movie) ON (m.embedding)
OPTIONS {indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'}}
```

```python
# generate_embeddings.py — parallel embedding generation
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = [executor.submit(process_movie, movie) for movie in movies]
    for future in as_completed(futures):
        result = future.result()
        if result:
            results_to_store.append(result)
```

```python
# vector_search.py — Haystack pipeline: embed query → Cypher retrieval
pipeline = Pipeline()
pipeline.add_component("query_embedder", text_embedder)
pipeline.add_component("retriever", retriever)
pipeline.connect("query_embedder.embedding", "retriever.query_embedding")
result = pipeline.run({
    "query_embedder": {"text": query},
    "retriever": {"query": cypher_query, "parameters": {"index": "overview_embeddings", "top_k": 3}},
})
```
