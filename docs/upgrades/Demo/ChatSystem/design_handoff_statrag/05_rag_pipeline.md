# 05 — RAG Pipeline Implementation Notes

This is the **backend contract** the UI assumes. Use this when implementing the actual system in Claude Code.

The UI was designed against a hybrid RAG pipeline over statistical/econometric textbooks. The system has three layers:

```
┌─────────────────────────────────────────────────────────────────┐
│  React UI (this design)                                         │
└─────────────────────────────────────────────────────────────────┘
                            ▲
                            │ SSE / REST
┌─────────────────────────────────────────────────────────────────┐
│  Orchestrator (Python / Node)                                   │
│   ├─ query rewriting                                            │
│   ├─ retrieval (sparse + dense + rerank)                        │
│   ├─ prompt assembly (with sources)                             │
│   ├─ LLM call (OpenAI / DeepSeek) — streaming                   │
│   └─ post-processing (cite, highlight spans, latency stats)     │
└─────────────────────────────────────────────────────────────────┘
                            ▲
                            │
┌──────────────────┬──────────────────┬───────────────────────────┐
│  Qdrant          │  Object store    │  LLM provider             │
│  (vector DB)     │  (figures, PDFs) │  (OpenAI/DeepSeek API)    │
│                  │                  │                           │
│  Collections per │  S3/MinIO/disk:  │  Streamed completions     │
│  book (chunks +  │  rendered fig    │  function/tool calls      │
│  figures).       │  thumbnails +    │  for structured output    │
│                  │  the source PDFs │                           │
└──────────────────┴──────────────────┴───────────────────────────┘
```

---

## Qdrant collections

One collection per book. Suggested names mirror the prototype:

```
islp_chunks
islp_figures
hansen_chunks
hansen_figures
esl_chunks         (future)
wooldridge_chunks  (future)
```

### Chunk payload (vector + metadata)

```json
{
  "id": "islp_ch06_p247_b3",
  "vector": [0.012, -0.034, ...],         // 1024-d from BAAI/bge-large-en-v1.5
  "payload": {
    "book": "ISLP",
    "chapter": "ch06",
    "section": "§6.2.2",
    "section_title": "The Bias-Variance Tradeoff",
    "page": 247,
    "block_index": 3,
    "text": "Why does ridge regression improve over least squares? Its advantage…",
    "tokens": 312,
    "sentences": [
      { "start": 0,   "end": 64,  "text": "Why does ridge regression…" },
      { "start": 65,  "end": 142, "text": "Its advantage is rooted in…" }
    ],
    "math_present": true,
    "figure_refs": ["fig_6_5"]
  }
}
```

### Figure payload

```json
{
  "id": "islp_fig_6_4",
  "vector": [...],                         // embed the caption + surrounding context
  "payload": {
    "book": "ISLP",
    "chapter": "ch06",
    "ref": "fig_6_4",
    "caption": "Bias-variance tradeoff as λ varies. Test MSE…",
    "context_chunk_id": "islp_ch06_p249_b1",
    "thumb_url": "s3://figures/islp/fig_6_4.png",
    "alt_text": "Three curves on a log-λ axis: variance decreases, bias² increases, test MSE U-shaped."
  }
}
```

---

## Retrieval

Hybrid (sparse + dense) is the design's assumption. Concretely:

1. **Query rewriting** (LLM cheap pass) — turn the raw user question into a retrieval-friendly query. Surface this rewritten string in `RetrievalMetadata.rewrittenQuery` so it shows in the ContextPanel accordion (debug visibility).
2. **Dense search** — embed the rewritten query (same model: `BAAI/bge-large-en-v1.5`), `top_k=20` per active collection.
3. **Sparse search** — BM25 over the same collections (Qdrant 1.10+ has native BM25; or use a Postgres FTS fallback).
4. **Hybrid score** — `0.7 · dense_score + 0.3 · sparse_score` (the default the UI displays). Configurable.
5. **Rerank** (optional) — cross-encoder over the top 20 → keep top 5–8.
6. **Filter** — apply book filter (only collections the user has selected) + score threshold (default 0.6).

Return:

```ts
{
  sources: Source[5..8],
  figures: Figure[0..3],            // any figures referenced by the chunks above
  metadata: RetrievalMetadata
}
```

---

## Highlight span generation

The SourceModal highlights the spans the LLM actually used. Two ways to generate these:

**Cheap (heuristic):** during retrieval, after getting the top-K chunks, run a sentence-level dense re-score with the original query. Mark the top 1–3 sentences per chunk as the highlight ranges. Return character offsets.

**Accurate (LLM-cited):** ask the LLM to emit sentence-level citations as it generates the answer (e.g. `[chunk_id, start, end]` tuples via a tool call). Post-process those into the highlights array. More expensive but the UI experience is dramatically better — the user sees exactly which sentences contributed.

The prototype assumes the **heuristic** path (highlights are computed at retrieval time, not generation time) because the chip-to-source link is generic. Pick based on budget.

In either case, **always return character ranges**, not raw substrings. The current prototype uses substrings as a placeholder.

---

## Streaming protocol

Use Server-Sent Events. The event sequence for a typical Tutor mode turn:

```
event: meta
data: {"type":"meta","mode":"tutor","books":["ISLP","HANSEN"],"sourceCount":3,"latencyMs":820,"model":"gpt-4o"}

event: token
data: {"type":"token","text":"Ridge "}

event: token
data: {"type":"token","text":"regression "}

event: token
data: {"type":"token","text":"extends "}

...

event: paragraph_break
data: {"type":"paragraph_break"}

event: math_block
data: {"type":"math_block","tex":"\\hat{\\beta}_{\\text{ridge}} = \\arg\\min_{\\beta} \\;\\bigl\\lVert y - X\\beta \\bigr\\rVert_2^2 + \\lambda \\bigl\\lVert \\beta \\bigr\\rVert_2^2"}

event: token
data: {"type":"token","text":"**Hansen "}

... (mid-paragraph, bold continues until matching `**`)

event: figure
data: {"type":"figure","ref":"fig_6_4","book":"ISLP","chapter":"ch06","caption":"…","chart":"https://figures.example.com/islp/fig_6_4.png"}

event: source_chip
data: {"type":"source_chip","book":"HANSEN","section":"ch07 §7.4"}

...

event: sources_full
data: {"type":"sources_full","sources":[ {…full Source…}, ... ]}

event: retrieval_meta
data: {"type":"retrieval_meta","meta":{…RetrievalMetadata…}}

event: done
data: {"type":"done"}
```

Notes:
- The `meta` event should fire as soon as retrieval completes (before any tokens). That's what the `0.8s` badge timer measures.
- Send `paragraph_break` rather than streaming a literal `\n\n` — gives the renderer explicit boundaries.
- `sources_full` and `figures_full` arrive in parallel with token streaming; the UI populates the right panel as it gets them. The inline `source_chip` events let chips fade in *under* the answer text in the right order (each chip tied to a paragraph).
- Heartbeat every ~15s if the LLM hasn't produced a token to keep the connection alive.

---

## Prompt assembly

Suggested system prompt skeleton for Tutor mode (adapt per mode):

```
You are statrag, a research-grade tutor that answers questions about statistics and
econometrics using ONLY the provided textbook excerpts. Cite specific sections inline
using the format **Book (chapter, section)** — never invent citations. Render mathematics
in LaTeX between $...$ for inline and $$...$$ for display equations.

Available textbooks:
- ISLP: An Introduction to Statistical Learning with Applications in Python
- HANSEN: Hansen's Econometrics (graduate level, theory-heavy)

The user is technical. Use precise notation. If two textbooks disagree on emphasis or
derivation, surface both perspectives and identify the difference.

Source excerpts (rank-ordered by relevance, with section paths):

{{#each sources}}
[#{{rank}}] {{book}} {{chapter}} {{section}} — {{title}} (score {{score}}):
{{chunk}}
---
{{/each}}

User question: {{message}}
```

Tool call (if you go the LLM-cited-highlights route): expose a `cite(chunk_id, char_start, char_end, reason)` function the model can call to mark spans. Aggregate the calls and emit `sources_full` with the highlights filled.

---

## Books index / "Not indexed" CTAs

The BookModal shows un-indexed books with a `+ Index` CTA. Behind that button:

```
POST /books/:id/index
→ { jobId: string }

GET /jobs/:jobId
→ { status: 'pending' | 'parsing' | 'embedding' | 'indexing' | 'complete' | 'error',
    progress: 0..1, message?: string }
```

Indexing flow (rough):
1. Parse PDF → page-aware text chunks (target 300–500 tokens, sentence-aligned).
2. Detect equations (LaTeX) and figure references; store as metadata.
3. Render figures from the PDF / source files → upload to object store.
4. Embed each chunk with `BAAI/bge-large-en-v1.5` (or whatever you pick consistently across the corpus).
5. Upsert into Qdrant under the book's collection.

The UI doesn't currently show a job progress modal — flag this for follow-up design.

---

## Performance targets

The prototype shows latency in the assistant mode badge (e.g. "0.8s"). For the design to feel right:

| Stage                    | Target          | Notes                                |
|--------------------------|-----------------|--------------------------------------|
| Time-to-first-meta       | ≤ 400ms         | First "meta" event after the user sends |
| Retrieval (hybrid + rerank) | ≤ 600ms      | This is what shows in the badge      |
| Time-to-first-token      | ≤ 1.5s          | After the meta event                 |
| End-to-end (avg answer)  | 3–8s            | Streaming hides most of this         |

Cache embeddings of the rewritten query string for 5min — repeat questions are common.

---

## Security & privacy

- The corpus is copyrighted material (textbooks). **Do not** expose endpoints that return raw chunk text without authentication.
- Source chunks shown to the user should be excerpts with clear attribution; the SourceModal already follows fair-use-ish conventions (excerpt with citation).
- LLM provider keys: server-side only. Never ship to the client.
- Conversation logs: store ciphertext at rest if multi-tenant.

---

End of handoff package. Open `design/statrag.html` in a browser to see the live reference, and refer back to these docs as you implement.
