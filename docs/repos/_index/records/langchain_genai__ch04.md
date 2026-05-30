# code:langchain_genai:ch04 — Building Intelligent RAG Systems

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch04
chapter_title: Building Intelligent RAG Systems
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter4

## Summary
Chapter 4 builds a complete end-to-end RAG system from embeddings through to a production-ready Streamlit app. Four notebooks cover OpenAI embeddings and vector stores, document loading and chunking strategies, vector/hybrid/MMR retrieval techniques, and advanced methods (query expansion, contextual compression, self-consistency checking with citations). The companion Python modules implement a reusable `DocumentLoader` supporting PDF/EPUB/DOCX/TXT, a `DocumentRetriever` backed by an in-memory vector store, a four-node LangGraph pipeline (retrieve → generate → double-check → finalise), and a Streamlit "CorpDocs with Citations" UI.

## Libraries & frameworks
chapter4, config, langchain, langchain_chroma, langchain_community, langchain_core, langchain_experimental, langchain_groq, langchain_openai, langchain_text_splitters, langgraph, logging, os, pathlib, streamlit, sys, tempfile, typing, typing_extensions

## Models & APIs
`llama-3.3-70b-versatile` via `ChatGroq` (retrieval chain LLM), `text-embedding-3-large` via `OpenAIEmbeddings` (with `CacheBackedEmbeddings`), `ChatOpenAI` (notebook query-expansion and evaluation chains), FAISS in-memory vector store, Chroma vector store, LangChain `InMemoryVectorStore`

## Concepts / patterns
RAG pipeline, embeddings and vector stores, document loading (multi-format), RecursiveCharacterTextSplitter, similarity search, MMR retrieval, query expansion/transformation, contextual compression retrieval, self-consistency citation checking, LangGraph four-node state machine with MemorySaver, LCEL chains, Streamlit chat UI for document Q&A.

## Files
- 01_embeddings_and_vectorstores.ipynb — Creates OpenAI embeddings for example sentences and stores them in vector stores; demonstrates cosine similarity comparison (py)
- 02_document_processing.ipynb — Loads a JSON knowledge base with JSONLoader and splits it using CharacterTextSplitter and RecursiveCharacterTextSplitter (py)
- 03_retrieval_techniques.ipynb — Implements basic vector search, hybrid search, and MMR retrieval with FAISS and query transformation chains (py)
- 04_advanced_rag_techniques.ipynb — Demonstrates query expansion, contextual compression, and self-consistency citation checking with format_sources_with_citations (py)
- README.md — Chapter overview with notebook descriptions and Streamlit app usage instructions (md)
- document_loader.py — Multi-format DocumentLoader (PDF, TXT, EPUB, DOCX) wrapping LangChain community loaders (py)
- llms.py — Instantiates ChatGroq llama-3.3-70b-versatile and CacheBackedEmbeddings wrapping text-embedding-3-large (py)
- rag.py — Four-node LangGraph pipeline: retrieve → generate → double_check → doc_finalizer with MemorySaver (py)
- retriever.py — DocumentRetriever (BaseRetriever subclass) backed by InMemoryVectorStore with split_documents helper (py)
- streamlit_app.py — "CorpDocs with Citations" Streamlit chat UI for document upload, retrieval, generation, and compliance checking (py)

## Code entities
- 04_advanced_rag_techniques.ipynb: format_sources_with_citations, generate_attributed_response, verify_response_accuracy
- document_loader.py: EpubReader, DocumentLoaderException, DocumentLoader, load_document
- rag.py: State, retrieve, generate, double_check, doc_finalizer
- retriever.py: split_documents, DocumentRetriever
- streamlit_app.py: process_message

## Key snippets
```python
# LangGraph RAG pipeline (rag.py)
class State(TypedDict):
    question: str
    context: List[Document]
    answer: str
    issues_report: str
    issues_detected: bool
    messages: Annotated[list, add_messages]

graph_builder = StateGraph(State).add_sequence(
    [retrieve, generate, double_check, doc_finalizer]
)
graph_builder.add_edge(START, "retrieve")
graph_builder.add_edge("doc_finalizer", END)
graph = graph_builder.compile(checkpointer=MemorySaver())
```

```python
# CacheBackedEmbeddings wrapping text-embedding-3-large (llms.py)
from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore
from langchain_openai import OpenAIEmbeddings

underlying_embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
EMBEDDINGS = CacheBackedEmbeddings.from_bytes_store(
    underlying_embeddings, LocalFileStore("./cache/"), namespace=underlying_embeddings.model
)
```
