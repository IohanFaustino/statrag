# code:neo4j_llm:ch02 — Demystifying RAG

book: Building Neo4j-Powered Applications with LLMs
slug: neo4j_llm
chapter: ch02
chapter_title: Demystifying RAG
repo: https://github.com/PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs (branch main)
folder: ch2

## Summary
Chapter 2 implements the core building blocks of Retrieval-Augmented Generation (RAG) from scratch using HuggingFace Transformers. The code progresses from BM25 keyword matching and DPR-based dense passage retrieval to full end-to-end pipelines where DPR retrieves top-k passages and a T5 generator synthesises an answer. A fine-tuning script adapts T5 on the PubMedQA dataset, and a semantic search pipeline over GitHub issues embeds documents with `all-MiniLM-L6-v2` and retrieves via cosine similarity.

## Libraries & frameworks
datasets, gc, numpy, os, pandas, rank_bm25, sklearn, torch, transformers

## Models & APIs
- `facebook/dpr-ctx_encoder-multiset-base` (DPR context encoder)
- `facebook/dpr-question_encoder-single-nq-base` (DPR question encoder)
- `facebook/dpr-reader-multiset-base` (DPR reader)
- `t5-small` (T5 conditional generation)
- `sentence-transformers/all-MiniLM-L6-v2` (semantic search embedder)

## Concepts / patterns
- BM25 keyword-based retrieval (`rank_bm25`)
- Dense Passage Retrieval (DPR) with bi-encoder architecture
- cosine similarity re-ranking over precomputed document embeddings
- RAG pipeline: retrieve-then-generate with T5
- fine-tuning a seq2seq model (T5) on PubMedQA
- CLS-pooling for sentence embeddings

## Files
- augmented_generation.py — Augmented generation demo: T5 answers a question conditioned on retrieved passages (py)
- dpr.py — DPR context encoder encodes a small corpus and retrieves top-k documents by dot-product similarity (py)
- fine_tune_rag.py — Fine-tunes T5-small on PubMedQA using HuggingFace Trainer for question-answering (py)
- full_rag_pipeline.py — Full semantic search pipeline: embeds GitHub-issue comments with MiniLM, retrieves by cosine similarity (py)
- integrate_and_generate.py — End-to-end RAG: DPR retrieves passages, T5 synthesises a final answer (py)
- keyword_matching.py — BM25Okapi keyword search over a toy corpus demonstrating sparse retrieval (py)
- passage_retrieval.py — Full DPR tri-encoder pipeline (question encoder + context encoder + reader) for passage ranking (py)
- vector_similarity_search.py — Vector similarity search using DPR question/context encoders and dot-product scoring (py)

## Code entities
- augmented_generation.py: generate_response
- dpr.py: encode_documents, retrieve_documents
- fine_tune_rag.py: preprocess_function
- full_rag_pipeline.py: concatenate_text, cls_pooling, get_embeddings
- integrate_and_generate.py: integrate_and_generate

## Key snippets

```python
# keyword_matching.py — BM25 sparse retrieval
bm25 = BM25Okapi(tokenized_corpus, k1=1.5, b=0.75)
scores = bm25.get_scores(query.split())
ranked_docs = sorted(zip(corpus, scores), key=lambda x: x[1], reverse=True)
```

```python
# dpr.py — DPR dense retrieval with cosine similarity
def retrieve_documents(query, num_results=3):
    inputs = tokenizer(query, return_tensors='pt', padding=True, truncation=True)
    query_embedding = model(**inputs).pooler_output.numpy()
    similarity_scores = cosine_similarity(query_embedding, document_embeddings).flatten()
    top_indices = similarity_scores.argsort()[-num_results:][::-1]
    return [(documents[i], similarity_scores[i]) for i in top_indices]
```

```python
# integrate_and_generate.py — RAG: DPR retrieval + T5 generation
def integrate_and_generate(query, retrieved_docs):
    input_text = f"Answer this question based on the following context: {query} Context: {' '.join(retrieved_docs)}"
    inputs = t5_tokenizer(input_text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    outputs = t5_model.generate(**inputs, max_length=100)
    return t5_tokenizer.decode(outputs[0], skip_special_tokens=True)
```
