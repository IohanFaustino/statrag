# code:rothman_rag:ch06 — Scaling RAG Bank Customer Data with Pinecone

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch06
chapter_title: Scaling RAG Bank Customer Data with Pinecone
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter06

## Summary
This chapter demonstrates scalable RAG over a 10,000-record bank customer churn dataset (Kaggle) using Pinecone as the production vector store. Pipeline 1 downloads the dataset via Kaggle API, performs EDA with matplotlib/seaborn, and trains a baseline ML model. Pipeline 2 converts each customer record to a text chunk, embeds all 10,000 chunks with `text-embedding-3-small` in batches, and upserts them into a Pinecone serverless index. Pipeline 3 queries the index by embedding a target customer profile and augments a GPT-4o prompt with the top retrieved matches.

## Libraries & frameworks
google, json, kaggle, matplotlib, openai, os, pandas, pinecone, seaborn, sklearn, sys, time, zipfile

## Models & APIs
`text-embedding-3-small` (OpenAI embeddings, 1536d), `gpt-4o` (OpenAI chat generation), Pinecone serverless index (`bank-index-50000`, cosine metric, AWS us-east-1)

## Concepts / patterns
Scalable RAG with Pinecone, batch embedding and upsert (10,000 records), tabular data as RAG corpus (each row serialised to text), serverless Pinecone index creation, target-vector querying, augmented generation over structured customer data, EDA before ingestion

## Files
- Pipeline_1_Collecting_and_preparing_the_dataset.ipynb — Downloads the Bank Customer Churn dataset from Kaggle, performs EDA (complaint/exit rates, age/salary distributions, heatmap), and saves the cleaned `data1.csv` (py)
- Pipeline_2_Scaling_a_Pinecone_Index.ipynb — Converts each row of the 10,000-record dataset to a text chunk, generates `text-embedding-3-small` embeddings in batches, and upserts all vectors into a Pinecone serverless index (py)
- Pipeline_3_RAG_Generative_AI.ipynb — Embeds a target customer profile, queries the Pinecone index for similar records, and passes the retrieved contexts to GPT-4o for augmented generative analysis (py)

## Code entities
- Pipeline_2_Scaling_a_Pinecone_Index.ipynb: get_embedding, embed_chunks, upsert_to_pinecone, get_batch_size, batch_upsert, display_results, get_embedding
- Pipeline_3_RAG_Generative_AI.ipynb: get_embedding

## Key snippets

```python
# Serialising each bank customer row as a text chunk for embedding
for index, row in data1.iterrows():
    row_data = [f"{col}: {row[col]}" for col in data1.columns]
    line = ' '.join(row_data)
    chunks.append(line)
# Example chunk: "CustomerId: 15634602 CreditScore: 619 Age: 42 ..."
```

```python
# Batch embedding with text-embedding-3-small
def get_embedding(texts, model="text-embedding-3-small"):
    texts = [text.replace("\n", " ") for text in texts]
    response = client.embeddings.create(input=texts, model=model)
    return [res.embedding for res in response.data]

embeddings = get_embedding(chunks, model=embedding_model)
```

```python
# Pinecone serverless index creation and upsert
pc = Pinecone(api_key=PINECONE_API_KEY)
spec = ServerlessSpec(cloud='aws', region='us-east-1')
if index_name not in pc.list_indexes().names():
    pc.create_index(index_name, dimension=1536, metric='cosine', spec=spec)
index = pc.Index(index_name)
# ... batch upsert vectors with metadata
index.upsert(vectors=batch)
```
