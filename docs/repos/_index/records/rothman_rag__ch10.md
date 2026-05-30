# code:rothman_rag:ch10 — RAG for Video Stock Production with Pinecone and OpenAI

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch10
chapter_title: RAG for Video Stock Production with Pinecone and OpenAI
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter10

## Summary
This chapter builds a three-pipeline multimodal RAG system for video stock production. Pipeline 1 splits sport videos into frames using OpenCV, generates GPT-4o Vision captions/comments per frame, and saves them as CSVs. Pipeline 2 embeds the frame comments with `text-embedding-3-small` and upserts them in batches to a Pinecone index. Pipeline 3 (the "Video Expert") queries Pinecone with an embedded user prompt, retrieves matching frame comments, augments a GPT-4o prompt, and evaluates responses with cosine similarity, spaCy similarity, F1/precision/recall, and a confusion matrix.

## Libraries & frameworks
IPython, PIL, base64, csv, cv2, google, io, matplotlib, numpy, openai, os, pandas, pinecone, requests, seaborn, sentence_transformers, shutil, sklearn, spacy, subprocess, sys, time, uuid

## Models & APIs
`gpt-4o` (OpenAI chat + vision for frame commenting and RAG generation), `text-embedding-3-small` (OpenAI embeddings, 1536d), Pinecone serverless index (`videos-index`, cosine), spaCy `en_core_web_md` (similarity evaluation)

## Concepts / patterns
Multimodal RAG (video frames → GPT-4o Vision captions → Pinecone → RAG generation), three-stage production pipeline (generate → store → retrieve+generate), batch Pinecone upsert of video frame embeddings, F1/precision/recall/confusion-matrix RAG evaluation, video-to-frame splitting with OpenCV, base64 frame encoding for Vision API

## Files
- Pipeline_1_Generator_and_Commentator.ipynb — Splits sport videos into frames with OpenCV, sends each frame as a base64 image to GPT-4o Vision to generate captions, and saves frame comments to CSV (py)
- Pipeline_2_The_Vector_Store_Administrator.ipynb — Embeds frame comments from Pipeline 1 using `text-embedding-3-small` and upserts them in batches into a Pinecone serverless index (py)
- Pipeline_3_The_Video_Expert.ipynb — Queries Pinecone with an embedded user prompt to retrieve matching frame comments, augments a GPT-4o prompt, and evaluates responses with cosine similarity, spaCy, F1/precision/recall, and confusion matrix (py)
- Video_dataset_visualization.ipynb — Utility notebook for downloading and displaying sport videos and individual frames from the dataset (py)
- frames/basketball3/text.txt — Pre-generated GPT-4o Vision text description of a basketball video frame used as a fixed retrieval example (txt)

## Code entities
- Pipeline_1_Generator_and_Commentator.ipynb: download, display_video, split_file, generate_comment, save_comment, generate_openai_comments, display_comments
- Pipeline_2_The_Vector_Store_Administrator.ipynb: download, get_embedding, upsert_in_batches, display_video
- Pipeline_3_The_Video_Expert.ipynb: download, get_embedding, query_pinecone, collect_query_results, get_openai_response, display_video, display_video_frame, display_frame, calculate_cosine_similarity_with_embeddings, spacy_similarity, calculate_cosine_similarity, extract_rewritten_comment
- Video_dataset_visualization.ipynb: download, download_video, display_video, display_video_frame

## Key snippets

```python
# Pipeline 1: Split video into frames and generate GPT-4o Vision comments
def generate_comment(frame_path):
    with open(frame_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "Describe the sport action in this frame."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
        ]}]
    )
    return response.choices[0].message.content
```

```python
# Pipeline 2: Embed comments and batch-upsert to Pinecone
def get_embedding(text, model="text-embedding-3-small"):
    response = client.embeddings.create(input=[text.replace("\n", " ")], model=model)
    return response.data[0].embedding

def upsert_in_batches(index, vectors, batch_size=100):
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i+batch_size]
        index.upsert(vectors=batch)
```

```python
# Pipeline 3: RAG query — embed prompt, retrieve from Pinecone, augment + generate
def query_pinecone(prompt, index, top_k=5):
    query_embedding = get_embedding(prompt)
    return index.query(vector=query_embedding, top_k=top_k, include_metadata=True)

results = query_pinecone(user_prompt, index)
context = "\n".join([m['metadata']['text'] for m in results['matches']])
augmented = f"Context:\n{context}\n\nQuestion: {user_prompt}"
answer = get_openai_response(augmented)
```
