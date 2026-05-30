# code:rothman_rag:ch03 — Building Index-Based RAG with LlamaIndex, Deep Lake, and OpenAI

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch03
chapter_title: Building Index-Based RAG with LlamaIndex, Deep Lake, and OpenAI
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter03

## Summary
This chapter demonstrates index-based RAG using LlamaIndex with a Deep Lake vector store over drone-technology documents scraped from GitHub, arXiv, and Wikipedia. The main notebook builds four index types — VectorStoreIndex, TreeIndex, ListIndex, and KeywordTableIndex — and compares their query performance with cosine-similarity metrics. A carry-over notebook from Chapter 02 shows the same Deep Lake RAG pipeline with the o3 model for cross-chapter comparison.

## Libraries & frameworks
IPython, bs4, deeplake, google, json, llama_index, markdown, numpy, openai, os, pandas, re, requests, sentence_transformers, sklearn, textwrap, time

## Models & APIs
`gpt-4o` (OpenAI LLM via LlamaIndex), `text-embedding-ada-002` (LlamaIndex default OpenAI embeddings), Deep Lake vector store (`hub://denis76/drone_v2`), `o3` (in the carry-over notebook)

## Concepts / patterns
Index-based RAG, LlamaIndex VectorStoreIndex, TreeIndex, ListIndex, KeywordTableIndex query engines, Deep Lake as LlamaIndex vector store backend, optimized chunking, node relationships in LlamaIndex, similarity-top-k retrieval, cosine-similarity performance metric comparison across index types

## Files
- 3_Augmented_Generation_o3.ipynb — Carry-over from Chapter 02 demonstrating the Deep Lake embedding-retrieval RAG pipeline with the o3 model (py)
- Deep_Lake_LlamaIndex_OpenAI_RAG.ipynb — Builds a Deep Lake vector store via LlamaIndex, creates four index types, queries each, and compares cosine-similarity metrics (py)

## Code entities
- 3_Augmented_Generation_o3.ipynb: embedding_function, get_user_prompt, search_query, wrap_text, call_gpt4_with_full_text, print_formatted_response, calculate_cosine_similarity, calculate_cosine_similarity_with_embeddings
- Deep_Lake_LlamaIndex_OpenAI_RAG.ipynb: clean_text, fetch_and_clean, display_record, calculate_cosine_similarity_with_embeddings, index_query, info_metrics

## Key snippets

```python
# Build Deep Lake vector store and create VectorStoreIndex via LlamaIndex
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Document
from llama_index.vector_stores.deeplake import DeepLakeVectorStore

vector_store = DeepLakeVectorStore(dataset_path="hub://denis76/drone_v2", overwrite=False)
storage_context = StorageContext.from_defaults(vector_store=vector_store)
index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
```

```python
# Index-based RAG query with similarity_top_k
def index_query(index, query, similarity_top_k=2):
    query_engine = index.as_query_engine(similarity_top_k=similarity_top_k)
    response = query_engine.query(query)
    return response

response = index_query(index, "How do drones detect objects?")
```

```python
# Comparing four index types for the same query
for index_type, idx in [("Vector", vector_index), ("Tree", tree_index),
                         ("List", list_index), ("Keyword", keyword_index)]:
    resp = index_query(idx, user_input)
    sim = calculate_cosine_similarity_with_embeddings(user_input, str(resp))
    info_metrics(index_type, sim)
```
