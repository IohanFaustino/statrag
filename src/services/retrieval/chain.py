"""LCEL RAG chain: retrieve -> prompt -> LLM -> structured response.

Returns both the answer and the source chunks used, so the CLI / UI layer can
render citations.
"""
from __future__ import annotations

from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_openai import ChatOpenAI

from src.core.config import settings
from src.services.retrieval.retrievers import build_retriever

SYSTEM_PROMPT = (
    "You are a careful statistics tutor. Answer using ONLY the provided context. "
    "If the context is insufficient, say so. Cite sources inline as [source]."
)

USER_TEMPLATE = (
    "Context:\n{context}\n\n"
    "Question: {question}\n\n"
    "Answer:"
)


class RAGResponse(TypedDict):
    answer: str
    sources: list[Document]


def _format_context(docs: list[Document]) -> str:
    """Concatenate retrieved chunks with their source tags."""
    parts: list[str] = []
    for d in docs:
        src = d.metadata.get("source", "unknown")
        parts.append(f"[{src}] {d.page_content}")
    return "\n\n".join(parts)


def build_chain(book_slug: str | None = None):
    """Return an LCEL Runnable that maps {question: str} -> RAGResponse."""
    retriever = build_retriever(book_slug=book_slug)
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("user", USER_TEMPLATE)]
    )
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0.0,
    )

    retrieve = retriever | (lambda docs: docs[: settings.top_k])

    answer_chain = (
        {
            "context": (lambda x: _format_context(x["sources"])),
            "question": (lambda x: x["question"]),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return RunnableParallel(
        {"sources": retrieve, "question": RunnablePassthrough()}
    ) | RunnableParallel({"answer": answer_chain, "sources": lambda x: x["sources"]})
