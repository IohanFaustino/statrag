# code:neo4j_llm:ch12 — Deploying Your Application on the Google Cloud

book: Building Neo4j-Powered Applications with LLMs
slug: neo4j_llm
chapter: ch12
chapter_title: Deploying Your Application on the Google Cloud
repo: https://github.com/PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs (branch main)
folder: ch12

## Summary
Chapter 12 packages the Haystack + Neo4j movie-recommendation chatbot from chapter 5 for cloud deployment. `app.py` is a production-hardened version of the Gradio chatbot that binds to `0.0.0.0:8080` for container routing. The Dockerfile wraps it as a `python:3.11` image, and the README provides step-by-step `gcloud` commands to build with Cloud Build, push to Artifact Registry, and deploy to Google Cloud Run with environment variable injection — with notes covering Azure Container Apps and AWS ECS as alternatives.

## Libraries & frameworks
dotenv, gradio, haystack, neo4j, neo4j_haystack, openai, os

## Models & APIs
- `text-embedding-ada-002` (OpenAI, 1536-dim, via `OpenAITextEmbedder`)
- Neo4j Aura vector index `overview_embeddings` (cosine, 1536-dim)
- `Neo4jDynamicDocumentRetriever` + `db.index.vector.queryNodes` Cypher

## Concepts / patterns
- containerisation of a Haystack RAG chatbot with Docker (python:3.11 base image)
- Google Cloud Run deployment via `gcloud builds submit` + `gcloud run deploy`
- Artifact Registry for Docker image hosting
- environment variable injection at deploy time from `.env` file
- Gradio interface served on container port 8080 (`server_name="0.0.0.0"`)
- Haystack pipeline: `OpenAITextEmbedder` → `Neo4jDynamicDocumentRetriever` for vector search

## Files
- Dockerfile — Containerises the Python 3.11 chatbot app, exposing port 8080 ()
- README.md — Step-by-step guide for Google Cloud Run deployment using gcloud CLI (md)
- app.py — Production Gradio chatbot: creates Neo4j vector index, embeds queries with `text-embedding-ada-002`, retrieves movies via Cypher vector search, serves on 0.0.0.0:8080 (py)
- requirements.txt — Pinned dependencies: haystack-ai==2.5.0, openai==1.67.0, gradio==4.44.1, neo4j==5.25.0, neo4j-haystack==2.0.3 (txt)

## Code entities
- app.py: create_or_reset_vector_index, perform_vector_search_cypher, chatbot

## Key snippets

```dockerfile
# Dockerfile — containerise Haystack chatbot
FROM python:3.11
EXPOSE 8080
WORKDIR /app
COPY . ./
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
```

```python
# app.py — Haystack Cypher vector search pipeline
cypher_query = """
    CALL db.index.vector.queryNodes("overview_embeddings", $top_k, $query_embedding)
    YIELD node AS movie, score
    MATCH (movie:Movie)
    RETURN movie.title AS title, movie.overview AS overview, score
"""
pipeline = Pipeline()
pipeline.add_component("query_embedder", embedder)
pipeline.add_component("retriever", retriever)
pipeline.connect("query_embedder.embedding", "retriever.query_embedding")
```

```bash
# README.md — deploy to Cloud Run
gcloud run deploy "$SERVICE_NAME" \
  --port=8080 \
  --image="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/$AR_REPO/$SERVICE_NAME" \
  --allow-unauthenticated \
  --region=$GCP_REGION \
  --platform=managed \
  --set-env-vars="GCP_PROJECT=$GCP_PROJECT,$ENV_VARS"
```
