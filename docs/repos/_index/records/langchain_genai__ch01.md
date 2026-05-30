# code:langchain_genai:ch01 — The Rise of Generative AI: From Language Models to Agents

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch01
chapter_title: The Rise of Generative AI: From Language Models to Agents
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter1

## Summary
Chapter 1 introduces tokenization as the fundamental building block of language models by walking through HuggingFace Transformers tokenization hands-on. The notebook loads a BERT tokenizer, encodes a sample sentence, decodes token IDs back to text, and prints the individual tokens — grounding readers in how LLMs process text before any LangChain code is shown.

## Libraries & frameworks
transformers

## Models & APIs
`bert-base-uncased` (HuggingFace tokenizer); `meta-llama/Meta-Llama-3-8B` (referenced as alternative tokenizer, not loaded)

## Concepts / patterns
Tokenization, subword encoding/decoding, AutoTokenizer from HuggingFace Transformers; conceptual framing of generative AI and LLM agents as context for the book.

## Files
- README.md — Chapter overview with Colab/Kaggle links for the tokenization notebook (md)
- tokenization.ipynb — Demonstrates BERT tokenization: encode a sentence, decode token IDs, print individual tokens (py)

## Code entities
(none detected)

## Key snippets
```python
from transformers import AutoTokenizer

model_name = "meta-llama/Meta-Llama-3-8B"
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

text = "The quick brown fox jumps over the lazy dog!"
encoded_text = tokenizer(text)

print(tokenizer.decode(encoded_text["input_ids"]))
print(encoded_text["input_ids"])
print(", ".join([tokenizer.decode(t) for t in encoded_text["input_ids"]]))
```
