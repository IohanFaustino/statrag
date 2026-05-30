# code:langchain_genai:ch02 — First Steps with LangChain

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch02
chapter_title: First Steps with LangChain
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter2

## Summary
Chapter 2 covers the core LangChain building blocks through five notebooks: invoking LLMs and chat models across multiple providers, composing prompt templates, wiring components together with LCEL pipe syntax, running local models via Ollama and HuggingFace Pipelines, and doing multimodal work (image generation with DALL-E 3 / Stable Diffusion and image understanding with GPT-4o-mini). By the end readers can build and compose basic chains using the full LangChain provider ecosystem.

## Libraries & frameworks
base64, config, langchain_anthropic, langchain_community, langchain_core, langchain_google_genai, langchain_huggingface, langchain_ollama, langchain_openai, os, sys

## Models & APIs
`gpt-4o-mini` (ChatOpenAI, image understanding), `ChatOpenAI` default (gpt-3.5/4 class, LCEL chains), `claude-3-opus-20240229` (ChatAnthropic), `gemini-2.0-flash` / `gemini-1.5-pro` / `gemini-pro` (ChatGoogleGenerativeAI / GoogleGenerativeAI), `deepseek-r1:1.5b` (ChatOllama local), `TinyLlama/TinyLlama-1.1B-Chat-v1.0` (HuggingFacePipeline local), `dall-e-3` (DallEAPIWrapper), `stability-ai/stable-diffusion-3.5-large` (Replicate)

## Concepts / patterns
LCEL pipe composition (`prompt | llm | output_parser`), PromptTemplate / ChatPromptTemplate, multi-provider LLM switching (OpenAI / Anthropic / Google / Ollama / HuggingFace), FakeListLLM for testing, multimodal image generation and vision understanding, sequential chain composition.

## Files
- LCEL.ipynb — Demonstrates LangChain Expression Language pipe syntax to compose prompt, LLM, and parser into chains (py)
- README.md — Chapter overview with per-notebook Colab/Kaggle links (md)
- chat_models.ipynb — Shows the unified LangChain chat-model interface across OpenAI, Anthropic, Google, and a FakeListLLM (py)
- local_models.ipynb — Runs local models via ChatOllama (deepseek-r1:1.5b) and HuggingFacePipeline (TinyLlama) (py)
- multimodal.ipynb — Generates images with DALL-E 3 and Stable Diffusion; understands images with GPT-4o-mini (py)
- prompts.ipynb — Builds PromptTemplate and ChatPromptTemplate chains with GoogleGenerativeAI and ChatOpenAI (py)

## Code entities
- multimodal.ipynb: analyze_image

## Key snippets
```python
# LCEL pipe chain
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

chain = PromptTemplate.from_template("Tell me a joke about {topic}") | ChatOpenAI() | StrOutputParser()
result = chain.invoke({"topic": "programming"})
```

```python
# Multi-provider switching via same interface
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

chat = ChatAnthropic(model="claude-3-opus-20240229")
messages = [
    SystemMessage(content="You're a helpful programming assistant"),
    HumanMessage(content="Write a Python function to calculate factorial")
]
response = chat.invoke(messages)
```

```python
# Image understanding with GPT-4o-mini
def analyze_image(image_url: str, question: str) -> str:
    chat = ChatOpenAI(model="gpt-4o-mini", max_tokens=256)
    message = HumanMessage(content=[
        {"type": "text", "text": question},
        {"type": "image_url", "image_url": {"url": image_url, "detail": "auto"}}
    ])
    return chat.invoke([message]).content
```
