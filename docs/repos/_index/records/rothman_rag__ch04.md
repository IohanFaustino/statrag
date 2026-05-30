# code:rothman_rag:ch04 — Multimodal Modular RAG for Drone Technology

book: RAG-Driven Generative AI
slug: rothman_rag
chapter: ch04
chapter_title: Multimodal Modular RAG for Drone Technology
repo: https://github.com/Denis2054/RAG-Driven-Generative-AI (branch main)
folder: Chapter04

## Summary
This chapter builds a multimodal modular RAG system for drone technology that combines two Deep Lake datasets — a text/LLM dataset queried via LlamaIndex and a vision dataset containing drone images with bounding-box labels. The notebook queries the text store with an LLM query engine, navigates the multimodal dataset to display images with bounding boxes drawn by OpenCV, encodes frames as base64 for GPT-4o Vision, and computes combined LLM + multimodal performance metrics.

## Libraries & frameworks
IPython, PIL, base64, cv2, deeplake, google, io, itertools, json, llama_index, numpy, openai, os, pandas, sentence_transformers, sklearn, textwrap, time

## Models & APIs
`gpt-4o` (OpenAI chat + vision via base64-encoded images), LlamaIndex VectorStoreIndex query engine, Deep Lake `hub://denis76/drone_v2` (LLM text dataset) + VisDrone image dataset

## Concepts / patterns
Multimodal RAG (text + image), modular RAG (two independent retrieval sources combined), bounding-box object detection overlaid on retrieved images, base64 image encoding for GPT-4o Vision, cosine-similarity metrics for LLM and multimodal retrieval separately, VisDrone dataset navigation

## Files
- Multimodal_Modular_RAG_Drones.ipynb — Implements a multimodal modular RAG pipeline that retrieves from a text/LLM Deep Lake index and a VisDrone image dataset, draws bounding boxes, and evaluates combined LLM and image retrieval performance (py)

## Code entities
- Multimodal_Modular_RAG_Drones.ipynb: display_image_with_bboxes, get_unique_words, process_and_display, display_source_image, calculate_cosine_similarity_with_embeddings, encode_image

## Key snippets

```python
# Multimodal dataset: loading Deep Lake LLM index and image dataset in parallel
import deeplake
dataset_path_llm = "hub://denis76/drone_v2"
ds_llm = deeplake.load(dataset_path_llm)

# LlamaIndex query engine over the text store
vector_store_index_llm = VectorStoreIndex.from_documents(documents_llm)
vector_query_engine_llm = vector_store_index_llm.as_query_engine(similarity_top_k=2)
llm_response = vector_query_engine_llm.query("How do drones identify a truck?")
```

```python
# Drawing bounding boxes from VisDrone dataset on retrieved image
def display_image_with_bboxes(image, bboxes, labels):
    for bbox, label in zip(bboxes, labels):
        x, y, w, h = bbox
        cv2.rectangle(image, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(image, label, (x, y-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return image
```

```python
# Encode image as base64 for GPT-4o Vision
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

image_data = encode_image(selected_image_path)
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": [
        {"type": "text", "text": user_input},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
    ]}]
)
```
