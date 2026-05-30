# code:rothman_rag:ch02 — RAG Embedding Vector Stores with Deep Lake and OpenAI

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch02
chapter_title: RAG Embedding Vector Stores with Deep Lake and OpenAI
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter02

## Summary
This chapter builds a complete three-stage RAG pipeline over Wikipedia space-exploration articles using Activeloop Deep Lake as the vector store. The first notebook scrapes and cleans 30 Wikipedia pages, the second creates a Deep Lake dataset and stores `text-embedding-3-small` embeddings, and the third performs embedding-based retrieval then calls GPT-4 for augmented generation with cosine-similarity evaluation. Three additional variant notebooks demonstrate the same RAG pipeline with GPT-4.5, o1-preview, and o3 models.

## Libraries & frameworks
IPython, bs4, deeplake, google, grequests, markdown, openai, os, re, requests, sentence_transformers, sklearn, subprocess, textwrap, time

## Models & APIs
`text-embedding-3-small` (OpenAI embeddings), `gpt-4o` / `gpt-4.5` / `o1-preview` / `o3` (OpenAI chat generation), Deep Lake vector store (`hub://denis76/space_exploration_v1`)

## Concepts / patterns
Embedding-based retrieval, Deep Lake vector store population and querying, three-stage RAG pipeline (collect → embed → retrieve+generate), cosine similarity evaluation of augmented vs non-augmented prompts, multi-model RAG variant comparison

## Files
- 1_Data_collection_preparation.ipynb — Scrapes and cleans 30 Wikipedia space-exploration articles using BeautifulSoup for use as the RAG corpus (py)
- 2_Embeddings_vector_store.ipynb — Chunks the collected text, generates `text-embedding-3-small` embeddings, and upserts them into an Activeloop Deep Lake vector store (py)
- 3_Augmented_Generation.ipynb — Queries Deep Lake with an embedding, retrieves top-k passages, augments the prompt, generates a response with GPT-4o, and evaluates with cosine similarity (py)
- 3_Augmented_Generation_GPT_4-5.ipynb — Same RAG pipeline as notebook 3 but using GPT-4.5 as the generator (py)
- 3_Augmented_Generation_o1_preview.ipynb — Same RAG pipeline as notebook 3 but using o1-preview as the generator (py)
- 3_Augmented_Generation_o3.ipynb — Same RAG pipeline as notebook 3 but using o3 as the generator (py)
- llm.txt — Pre-collected text corpus about LLMs used as an alternative RAG data source (txt)

## Code entities
- 1_Data_collection_preparation.ipynb: clean_text, fetch_and_clean
- 2_Embeddings_vector_store.ipynb: embedding_function
- 3_Augmented_Generation.ipynb: embedding_function, get_user_prompt, search_query, wrap_text, call_gpt4_with_full_text, print_formatted_response, calculate_cosine_similarity, calculate_cosine_similarity_with_embeddings
- 3_Augmented_Generation_GPT_4-5.ipynb: embedding_function, get_user_prompt, search_query, wrap_text, call_gpt4_with_full_text, print_formatted_response, calculate_cosine_similarity, calculate_cosine_similarity_with_embeddings
- 3_Augmented_Generation_o1_preview.ipynb: embedding_function, get_user_prompt, search_query, wrap_text, call_gpt4_with_full_text, print_formatted_response, calculate_cosine_similarity, calculate_cosine_similarity_with_embeddings
- 3_Augmented_Generation_o3.ipynb: embedding_function, get_user_prompt, search_query, wrap_text, call_gpt4_with_full_text, print_formatted_response, calculate_cosine_similarity, calculate_cosine_similarity_with_embeddings

## Key snippets

```python
# Embedding function using text-embedding-3-small
def embedding_function(texts, model="text-embedding-3-small"):
    if isinstance(texts, str):
        texts = [texts]
    texts = [t.replace("\n", " ") for t in texts]
    return [data.embedding for data in openai.embeddings.create(input=texts, model=model).data]
```

```python
# Deep Lake vector store retrieval + augmented generation
vector_store = VectorStore(path="hub://denis76/space_exploration_v1")
user_prompt = "Tell me about space exploration on the Moon and Mars."
search_results = vector_store.search(embedding_data=user_prompt, embedding_function=embedding_function)
top_text = search_results['text'][0].strip()
augmented_prompt = f"Context:\n{top_text}\n\nQuestion: {user_prompt}"
response = call_gpt4_with_full_text([augmented_prompt])
print_formatted_response(response)
```

```python
# Cosine similarity evaluation comparing augmented vs plain response
cos_sim_plain = calculate_cosine_similarity(user_prompt, plain_response)
cos_sim_augmented = calculate_cosine_similarity_with_embeddings(user_prompt, augmented_response)
print(f"Plain similarity: {cos_sim_plain:.4f}")
print(f"Augmented similarity: {cos_sim_augmented:.4f}")
```
