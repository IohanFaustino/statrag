# code:rothman_rag:ch08 — Dynamic RAG with Chroma and Hugging Face Llama

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch08
chapter_title: Dynamic RAG with Chroma and Hugging Face Llama
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter08

## Summary
This chapter implements Dynamic RAG using ChromaDB as an in-memory ephemeral vector store with Hugging Face's Llama-2-7b-chat-hf as the local generator. The notebook loads the SciQ science QA dataset, merges correct answers with supporting explanations into completions, embeds them with `all-MiniLM-L6-v2`, and upserts to a Chroma collection. It then retrieves the top supporting completion for a query using Chroma's query API and passes it to the Llama-2 pipeline for RAG generation, measuring session time across the full dynamic cycle.

## Libraries & frameworks
chromadb, datasets, google, numpy, os, pandas, spacy, textwrap, time, torch, transformers

## Models & APIs
`meta-llama/Llama-2-7b-chat-hf` (Hugging Face text-generation pipeline, float16 GPU), `all-MiniLM-L6-v2` (sentence-transformers, 384d, used as ChromaDB embedding function), SciQ dataset (Hugging Face `datasets`), ChromaDB in-memory client

## Concepts / patterns
Dynamic RAG (ephemeral in-memory vector store, real-time session), ChromaDB collection creation and querying, local open-source LLM generation (Llama-2), spaCy text similarity, SciQ dataset processing, session-time measurement for full RAG lifecycle

## Files
- Dynamic_RAG_with_Chroma_and_Hugging_Face.ipynb — Builds a dynamic RAG system over the SciQ dataset using ChromaDB as ephemeral vector store and Llama-2-7b-chat-hf as the local generator, with spaCy similarity evaluation (py)

## Code entities
- Dynamic_RAG_with_Chroma_and_Hugging_Face.ipynb: simple_text_similarity, LLaMA2

## Key snippets

```python
# Load SciQ, build completions, embed + store in ChromaDB
from datasets import load_dataset
import chromadb

dataset = load_dataset("sciq", split="train")
filtered_dataset = dataset.filter(lambda x: x["support"] != "" and x["correct_answer"] != "")
df = pd.DataFrame(filtered_dataset)
df['completion'] = df['correct_answer'] + " because " + df['support']

client = chromadb.Client()
collection = client.create_collection("sciq_supports6")
# ChromaDB uses all-MiniLM-L6-v2 by default
collection.add(documents=df['completion'].tolist(), ids=[str(i) for i in df.index])
```

```python
# ChromaDB retrieval + Llama-2 RAG generation
query = "Millions of years ago, plants used energy from the sun to form what?"
results = collection.query(query_texts=[query], n_results=1)
support = results['documents'][0][0]

augmented_prompt = f"Context: {support}\n\nQuestion: {query}\nAnswer:"
sequences = pipeline(augmented_prompt, max_length=512, do_sample=True, temperature=0.7)
print(sequences[0]['generated_text'])
```

```python
# Hugging Face Llama-2 pipeline setup
from transformers import AutoTokenizer
import transformers, torch

model = "meta-llama/Llama-2-7b-chat-hf"
tokenizer = AutoTokenizer.from_pretrained(model)
pipeline = transformers.pipeline(
    "text-generation", model=model,
    torch_dtype=torch.float16, device_map="auto"
)
```
