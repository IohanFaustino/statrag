# code:rothman_rag:ch07 — Building Scalable Knowledge-Graph-Based RAG with Wikipedia API and LlamaIndex

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch07
chapter_title: Building Scalable Knowledge-Graph-Based RAG with Wikipedia API and LlamaIndex
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter07

## Summary
This chapter builds a Knowledge-Graph-based RAG system using LlamaIndex's `KnowledgeGraphIndex` backed by a Deep Lake vector store, with documents sourced from Wikipedia via the `wikipedia-api` library. The main notebook builds a graph index over marketing/topic documents, visualises it with PyVis, performs re-ranking of query results, and computes detailed retrieval statistics (mean, median, IQR, percentile). Two supporting notebooks explore the Wikipedia API for data collection and NetworkX-based tree-to-graph conversion for understanding graph structures.

## Libraries & frameworks
IPython, PIL, bs4, datetime, deeplake, google, io, json, llama_index, matplotlib, networkx, nltk, numpy, openai, os, pandas, pyvis, re, requests, sentence_transformers, sklearn, subprocess, sys, textwrap, time, wikipediaapi

## Models & APIs
`gpt-4o` (OpenAI LLM via LlamaIndex), `text-embedding-ada-002` (LlamaIndex default embeddings), Deep Lake vector store, LlamaIndex `KnowledgeGraphIndex`, Wikipedia API (`wikipedia-api`)

## Concepts / patterns
Knowledge-Graph-based RAG, LlamaIndex KnowledgeGraphIndex, graph index visualisation with PyVis/NetworkX, re-ranking of retrieved nodes, Wikipedia API data collection with token counting, tree-to-graph conversion (NetworkX DiGraph), retrieval quality statistics (mean/median/IQR), citation URL collection per topic

## Files
- Knowledge_Graph__Deep_Lake_LlamaIndex_OpenAI_RAG.ipynb — Builds a LlamaIndex KnowledgeGraphIndex over Wikipedia-sourced documents stored in Deep Lake, visualises the graph with PyVis, re-ranks query results, and computes retrieval metrics (py)
- Tree_2_Graph.ipynb — Educational notebook showing how to convert hierarchical tree structures to directed graphs using NetworkX, with friendship-based edge styling (py)
- Wikipedia_API.ipynb — Uses the `wikipedia-api` library to retrieve article summaries and linked URLs for topics such as Marketing, Alan Turing, and Mark Twain, counting tokens per article (py)
- citations/AlanTuring_citations.txt — Pre-collected citation text for the Alan Turing Wikipedia topic (txt)
- citations/AlanTuring_urls.txt — Pre-collected Wikipedia link URLs for the Alan Turing topic (txt)
- citations/MarkTwain_citations.txt — Pre-collected citation text for the Mark Twain Wikipedia topic (txt)
- citations/MarkTwain_urls.txt — Pre-collected Wikipedia link URLs for the Mark Twain topic (txt)
- citations/Marketing_citations.txt — Pre-collected citation text for the Marketing Wikipedia topic (txt)
- citations/Marketing_urls.txt — Pre-collected Wikipedia link URLs for the Marketing topic (txt)

## Code entities
- Knowledge_Graph__Deep_Lake_LlamaIndex_OpenAI_RAG.ipynb: version_tuple, download, clean_text, fetch_and_clean, display_record, execute_query, calculate_cosine_similarity_with_embeddings
- Tree_2_Graph.ipynb: build_tree_from_pairs, check_relationships, draw_tree
- Wikipedia_API.ipynb: nb_tokens

## Key snippets

```python
# Build LlamaIndex KnowledgeGraphIndex backed by Deep Lake
from llama_index.core import KnowledgeGraphIndex
from llama_index.vector_stores.deeplake import DeepLakeVectorStore

vector_store = DeepLakeVectorStore(dataset_path="hub://denis76/marketing_v1")
storage_context = StorageContext.from_defaults(vector_store=vector_store)
kg_index = KnowledgeGraphIndex.from_documents(
    documents, storage_context=storage_context, max_triplets_per_chunk=2
)
```

```python
# Query the knowledge graph index
def execute_query(kg_index, query):
    query_engine = kg_index.as_query_engine(
        include_text=True, response_mode="tree_summarize",
        embedding_mode="hybrid", similarity_top_k=5
    )
    return query_engine.query(query)
```

```python
# Wikipedia API: collect links and count tokens
wiki = wikipediaapi.Wikipedia(language='en', user_agent='Knowledge/1.0')
page = wiki.page("Marketing")
for link in list(page.links.keys())[:maxl]:
    linked_page = wiki.page(link)
    nbt = nb_tokens(linked_page.summary)
    urls.append(linked_page.fullurl)
```
