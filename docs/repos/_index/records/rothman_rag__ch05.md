# code:rothman_rag:ch05 — Boosting RAG Performance with Expert Human Feedback

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch05
chapter_title: Boosting RAG Performance with Expert Human Feedback
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter05

## Summary
This chapter implements Hybrid Adaptive RAG where the retrieval strategy is dynamically selected based on a user-ranking score. The notebook fetches Wikipedia articles on LLMs and prompt engineering, then routes generation through one of three paths depending on a 1–5 ranking: no RAG (rank 1–2), human expert feedback injected into the prompt (rank 3–4), or standard RAG (rank 5). It includes a feedback collection loop with cosine-similarity evaluation and icon-based visual display of results.

## Libraries & frameworks
IPython, base64, bs4, google, grequests, numpy, openai, os, re, requests, sklearn, subprocess, textwrap, time

## Models & APIs
`gpt-4o` (OpenAI chat generation), `text-embedding-ada-002` (implicit via sklearn cosine similarity on embeddings), no external vector store — retrieval is keyword-matched Wikipedia fetch

## Concepts / patterns
Adaptive RAG (human-ranking-driven strategy selection), Human Feedback RAG (expert flashcard injection), hybrid retrieval (keyword-matched Wikipedia + expert corpus), cosine-similarity response evaluation, feedback persistence, retrieval-strategy branching

## Files
- Adaptive_RAG.ipynb — Implements a Hybrid Adaptive RAG pipeline that selects no-RAG, human-feedback-RAG, or standard-RAG based on a 1–5 user/expert ranking, with GPT-4o generation and cosine-similarity evaluation (py)
- human_feedback.txt — Expert flashcard corpus injected into the prompt for human-feedback RAG (rank 3–4) (txt)
- raw_markdown_rag.txt — Raw retrieved markdown content used as the standard RAG corpus (txt)

## Code entities
- Adaptive_RAG.ipynb: fetch_and_clean, process_query, call_gpt4_with_full_text, print_formatted_response, calculate_cosine_similarity, evaluate_response, image_to_data_uri, display_icons, save_feedback

## Key snippets

```python
# Adaptive RAG: routing by human-expert ranking score
ranking = 3  # simulated mean panel score

if ranking <= 2:
    # No RAG — direct LLM generation
    augmented_input = user_input
elif ranking <= 4:
    # Human expert feedback RAG
    with open("human_feedback.txt", "r") as f:
        expert_context = f.read()
    augmented_input = f"Expert feedback:\n{expert_context}\n\nQuestion: {user_input}"
else:
    # Standard RAG — Wikipedia retrieval
    cleaned_text = fetch_and_clean(urls[matched_keyword])
    augmented_input = f"Context:\n{cleaned_text[:2000]}\n\nQuestion: {user_input}"

response = call_gpt4_with_full_text([augmented_input])
```

```python
# Cosine similarity evaluation of retrieval quality
def evaluate_response(user_input, response):
    sim = calculate_cosine_similarity(user_input, response)
    print(f"Cosine similarity (query vs response): {sim:.4f}")
    return sim
```

```python
# Saving human feedback for future RAG enhancement
def save_feedback(user_rating, response, filename="human_feedback.txt"):
    with open(filename, "a") as f:
        f.write(f"Rating: {user_rating}\n")
        f.write(f"Response: {response}\n\n")
```
