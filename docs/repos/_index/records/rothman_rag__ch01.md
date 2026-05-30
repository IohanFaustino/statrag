# code:rothman_rag:ch01 — Why Retrieval Augmented Generation?

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch01
chapter_title: Why Retrieval Augmented Generation?
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter01

## Summary
This chapter introduces Naive, Advanced, and Modular RAG through educational examples using a small in-memory document corpus about RAG concepts. It walks through three progressively more sophisticated retrieval strategies — keyword search, TF-IDF vector search, and index-based search — combining them in a `RetrievalComponent` class that implements modular RAG. A companion notebook replaces the OpenAI generator with the xAI Grok-beta model to demonstrate provider interchangeability.

## Libraries & frameworks
collections, google, json, nltk, numpy, openai, os, pandas, requests, sklearn, spacy, textwrap

## Models & APIs
`gpt-4o` (OpenAI chat), `grok-beta` (xAI, via REST API), `text-embedding-ada-002` (implicit via sklearn TF-IDF; no dense embedding model called directly in this chapter)

## Concepts / patterns
Naive RAG (keyword search → augmented prompt → LLM generation), Advanced RAG (TF-IDF vector search + index-based search), Modular RAG (pluggable retriever strategies combined in `RetrievalComponent`), cosine similarity evaluation, synonym-expanded similarity scoring, retrieval metrics comparison

## Files
- RAG_Overview.ipynb — End-to-end tutorial implementing Naive, Advanced, and Modular RAG with GPT-4o as the generator and sklearn-based retrievers (py)
- RAG_Overview_Grok.ipynb — Same pipeline as RAG_Overview.ipynb but with the generator swapped to xAI Grok-beta via direct REST API calls (py)

## Code entities
- RAG_Overview.ipynb: call_llm_with_full_text, print_formatted_response, calculate_cosine_similarity, get_synonyms, preprocess_text, expand_with_synonyms, calculate_enhanced_similarity, find_best_match_keyword_search, find_best_match, setup_vectorizer, find_best_match, setup_vectorizer, RetrievalComponent
- RAG_Overview_Grok.ipynb: call_llm_with_full_text, print_formatted_response, calculate_cosine_similarity, get_synonyms, preprocess_text, expand_with_synonyms, calculate_enhanced_similarity, find_best_match_keyword_search, find_best_match, setup_vectorizer, find_best_match, setup_vectorizer, RetrievalComponent

## Key snippets

```python
# Modular RAG: pluggable retriever combining keyword, vector, and index search
class RetrievalComponent:
    def __init__(self, strategy='keyword'):
        self.strategy = strategy
        self.vectorizer = None
        self.tfidf_matrix = None
        self.documents = []

    def fit(self, documents):
        self.documents = documents
        if self.strategy in ('vector', 'index'):
            self.vectorizer, self.tfidf_matrix = setup_vectorizer(documents)

    def retrieve(self, query):
        if self.strategy == 'keyword':
            return find_best_match_keyword_search(query, self.documents)
        elif self.strategy == 'vector':
            return find_best_match(query, self.documents, self.vectorizer, self.tfidf_matrix)
        elif self.strategy == 'index':
            return find_best_match(query, self.documents, self.vectorizer, self.tfidf_matrix)
```

```python
# Naive RAG: augmented generation with keyword-matched context
best_match = find_best_match_keyword_search(user_query, db_records)
augmented_input = [f"Context: {best_match}", f"Question: {user_query}"]
response = call_llm_with_full_text(augmented_input)
print_formatted_response(response)
```

```python
# xAI Grok-beta generator (RAG_Overview_Grok.ipynb)
def call_llm_with_full_text(itext):
    url = "https://api.x.ai/v1/chat/completions"
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {os.getenv('xAI_KEY')}"}
    data = {"messages": [{"role": "system", "content": "You are a test assistant."},
                          {"role": "user", "content": itext}],
            "model": "grok-beta", "stream": False, "temperature": 0}
    response = requests.post(url, headers=headers, data=json.dumps(data))
    return response.json()['choices'][0]['message']['content']
```
