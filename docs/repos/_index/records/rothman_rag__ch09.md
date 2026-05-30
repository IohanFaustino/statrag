# code:rothman_rag:ch09 — Empowering AI Models: Fine-Tuning RAG Data and Human Feedback

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch09
chapter_title: Empowering AI Models: Fine-Tuning RAG Data and Human Feedback
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter09

## Summary
This chapter demonstrates fine-tuning GPT-4o-mini on the SciQ science QA dataset to embed domain knowledge directly into model weights, reducing reliance on runtime retrieval. The notebook downloads SciQ from Hugging Face, converts each QA pair (question + correct answer + support explanation) into the OpenAI fine-tuning JSONL chat format, uploads the file via the Files API, launches a fine-tuning job, monitors its status, and runs the resulting model in the OpenAI Playground.

## Libraries & frameworks
datasets, google, json, jsonlines, openai, os, pandas, textwrap

## Models & APIs
`gpt-4o-mini` (OpenAI fine-tuning base model), OpenAI Files API (fine-tune dataset upload), OpenAI Fine-Tuning API (job creation and monitoring), SciQ dataset (Hugging Face `datasets`)

## Concepts / patterns
Fine-tuning as a complement to RAG (knowledge baked into weights), OpenAI JSONL fine-tuning format (system/user/assistant chat turns), SciQ dataset preparation for instruction fine-tuning, fine-tune job monitoring, RAG + fine-tuning synergy

## Files
- Fine_tuning_OpenAI_GPT-4o-mini.ipynb — Prepares SciQ QA data in OpenAI JSONL fine-tuning format, uploads it, launches a gpt-4o-mini fine-tuning job, monitors completion, and tests the fine-tuned model (py)

## Code entities
(none detected)

## Key snippets

```python
# Convert SciQ to OpenAI fine-tuning JSONL format
items = []
for idx, row in df.iterrows():
    detailed_answer = row['correct_answer'] + " Explanation: " + row['support']
    items.append({
        "messages": [
            {"role": "system", "content": "Given a science question, provide the correct answer with a detailed explanation."},
            {"role": "user", "content": row['question']},
            {"role": "assistant", "content": detailed_answer}
        ]
    })
with jsonlines.open('/content/QA_prompts_and_completions.json', 'w') as writer:
    writer.write_all(items)
```

```python
# Upload file and launch fine-tuning job
from openai import OpenAI
client = OpenAI()

result_file = client.files.create(
    file=open("QA_prompts_and_completions.json", "rb"),
    purpose="fine-tune"
)
fine_tune_job = client.fine_tuning.jobs.create(
    training_file=result_file.id,
    model="gpt-4o-mini"
)
print(fine_tune_job)
```

```python
# Monitor fine-tuning job status
jobs = client.fine_tuning.jobs.list(limit=10)
first_non_empty_model = next(
    (job.fine_tuned_model for job in jobs.data if job.fine_tuned_model), None
)
print("Fine-tuned model:", first_non_empty_model)
```
