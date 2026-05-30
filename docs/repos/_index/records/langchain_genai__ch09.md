# code:langchain_genai:ch09 — Production-Ready LLM Deployment and Observability

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch09
chapter_title: Production-Ready LLM Deployment and Observability
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter9

## Summary
Chapter 9 covers the full production stack for LLM applications: serving, distributed indexing, and observability. The FastAPI module implements a REST + WebSocket server with streaming via `claude-3-sonnet` and `AsyncIteratorCallbackHandler`. The Ray subpackage shows distributed FAISS index building (crawl → chunk → parallel embed → merge shards) and Ray Serve deployment of a `SearchDeployment` backed by `sentence-transformers/all-MiniLM-L6-v2`. Additional scripts demonstrate PromptWatch prompt tracking, LangChain agent tracing with `return_intermediate_steps`, and a Lanarky streaming chat server. The chapter covers both horizontal scale (Ray parallelism) and observability tooling (LangSmith, PromptWatch).

## Libraries & frameworks
asyncio, bs4, config, fastapi, html, json, lanarky, langchain, langchain_anthropic, langchain_community, langchain_core, langchain_huggingface, langchain_openai, langchain_text_splitters, logging, numpy, os, pickle, promptwatch, pydantic, ray, re, requests, search_engine, starlette, subprocess, sys, time, traceback, typing, urllib, utils, uvicorn

## Models & APIs
`claude-3-sonnet-20240229` (ChatAnthropic — FastAPI WebSocket streaming server), `ChatOpenAI` default / `gpt-3.5-turbo-0613` (tracing agent), `sentence-transformers/all-MiniLM-L6-v2` (HuggingFaceEmbeddings — Ray Serve SearchDeployment), `OpenAIEmbeddings` (indexing.py FAISS index build), FAISS vector store, Ray Serve distributed deployment

## Concepts / patterns
FastAPI REST + WebSocket endpoints with streaming (`AsyncIteratorCallbackHandler`), Ray distributed FAISS index building (sharded `process_shard` remote tasks, shard merge), Ray Serve `SearchDeployment` for scalable vector search, PromptWatch prompt tracking, LangChain agent tracing with `return_intermediate_steps`, Lanarky streaming chat router, ConversationChain SSE, production deployment patterns (uvicorn, Docker-ready).

## Files
- README.md — Chapter overview with per-file descriptions and run instructions (md)
- chat.py — Lanarky-based streaming chat server with ConversationChain, HTTP and WebSocket routes, served on FastAPI (py)
- fastapi/main.py — Production FastAPI app with REST /chat endpoint (claude-3-sonnet) and /ws WebSocket streaming with AsyncIteratorCallbackHandler (py)
- indexing.py — Web crawler (RecursiveUrlLoader) + Ray-parallel FAISS index builder: chunk_docs, create_db, process_shard (ray.remote), create_db_parallel (py)
- prompt_tracking.py — Integrates PromptWatch for monitoring LLM prompt/response pairs in production (py)
- ray/build_index.py — Standalone Ray script: crawls Ray docs, embeds chunks in parallel via HuggingFaceEmbeddings, saves FAISS index (py)
- ray/serve_index.py — Ray Serve SearchDeployment that loads a pre-built FAISS index and serves similarity_search_with_score via HTTP (py)
- ray/test_client.py — Test client that sends queries to the Ray Serve search endpoint (py)
- ray/utils.py — HTML cleaning utility (clean_html_content) for web-crawled documents (py)
- serve_vector_store.py — VectorSearchDeployment: alternative Ray Serve wrapper for vector store semantic search (py)
- tracing.py — Agent tracing demo: ping tool + ChatOpenAI agent with return_intermediate_steps for observability (py)
- utils.py — Shared utility functions for the chapter (py)

## Code entities
- chat.py: create_chain, get
- fastapi/main.py: get, chat, websocket_endpoint
- indexing.py: chunk_docs, create_db, process_shard, create_db_parallel
- ray/build_index.py: preprocess_documents, embed_chunks_with_progress, build_index
- ray/serve_index.py: SearchDeployment, search
- ray/test_client.py: test_search
- ray/utils.py: clean_html_content
- serve_vector_store.py: VectorSearchDeployment
- tracing.py: ping

## Key snippets
```python
# FastAPI WebSocket streaming with AsyncIteratorCallbackHandler (fastapi/main.py)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    callback_handler = AsyncIteratorCallbackHandler()
    streaming_llm = ChatAnthropic(
        model="claude-3-sonnet-20240229", streaming=True, callbacks=[callback_handler]
    )
    task = asyncio.create_task(streaming_llm.ainvoke([HumanMessage(content=user_message)]))
    async for token in callback_handler.aiter():
        await websocket.send_json({"sender": "bot", "message_type": "stream", "message": token})
    await task
```

```python
# Ray-parallel FAISS index sharding (indexing.py)
@ray.remote
def process_shard(chunks: list[Document]):
    return FAISS.from_documents(documents=chunks, embedding=get_embeddings())

def create_db_parallel(chunks):
    shards = np.array_split(chunks, 8)
    ray.init()
    futures = [process_shard.remote(shard) for shard in shards]
    results = ray.get(futures)
    db = results[0]
    for result in results[1:]:
        db.merge_from(result)
    ray.shutdown()
    return db
```
