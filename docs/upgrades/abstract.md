# RAG Chat System — Part 2: Abstract

> Conceptual design document for the conversational and agentic layer built on top of the existing RAG pipeline for statistical textbooks.

---

## Context

The ingestion layer (Part 1) is complete. Qdrant holds hybrid-indexed chunks (dense + sparse) from **25 textbooks** across 6 fields (introduction, econometrics, math, ml_dp, risk, causal_inference) plus per-field image collections with figure captions (**8083 figures total**). Part 2 defines the services that consume this data.

> **Status update 2026-05-19**: image library expanded from 1 → 25 books (30× growth, 271 → 8083 pts). New `src/ingestion/ingest_images_only.py` module supports both VLM-format and EPUB-format markdown sources. See [feature 40](../services/chat-features/40-image-only-ingest.md).

---

## Shared Backbone

All services inherit the same retrieval pipeline:

```
User input
    ↓
[Query Processor]      ← mode detection, query rewriting
    ↓
[Hybrid Retriever]     ← dense (text-embedding-3-large) + sparse (BM25)
    ↓                     with optional theme / book / chapter filters
[Context Assembler]    ← ranks, deduplicates, fits token budget
    ↓
[LLM]                  ← GPT or DeepSeek depending on cost/quality
    ↓
[Output Formatter]     ← mode-specific schema (text, YAML, JSON, markdown)
```

Each service is a specialization of this backbone — same retrieval infrastructure, different system prompt and output schema. Switching between services at runtime is a **modal switch**, not a new system.

---

## Modal Architecture

The chat system exposes a single interface with switchable modes:

| Mode | Icon | What it does |
|---|---|---|
| Tutor | 📖 | Conversational Q&A with memory |
| Cross-book | 🔀 | Compares how both books treat the same concept |
| Figure-aware | 🖼️ | Includes relevant figures alongside answers |
| Quiz | 📝 | Generates exercises from a section |
| Navigator | 🔍 | Finds where a concept lives in the books |
| Prereq tracer | 🗺️ | Maps what you need before reading a section |
| Annotated reading | ✍️ | Explains terms in text you paste |
| Research assistant | 🔬 | Relates a paper excerpt to your textbooks |
| Math explainer | ∑ | Answers with rendered equations and figures |
| Study path | 📅 | Builds a personalized reading curriculum |
| Roadmap | 🎬 | Produces a video production brief for your content |

---

## Service Architectures

### 1. Conversational Textbook Tutor
**Architecture**: Single agent with memory buffer

Maintains conversation history across turns. A query rewriter converts the accumulated context into a retrieval-friendly query before each Qdrant call. Supports three memory strategies: sliding window (simple), summary compression (medium), or embedding conversation history into a separate Qdrant collection (long-term).

**Critical problems**:
- Context window bloat as history and retrieved chunks accumulate
- Retrieval drift: late-turn queries no longer reflect the user's actual need without rewriting
- Silent hallucination of precise statistical definitions requires mandatory source attribution

---

### 2. Cross-Book Comparison Mode
**Architecture**: Single agent, dual retrieval path

Rewrites the user query into two sub-queries (one per book), retrieves in parallel, merges and deduplicates, then synthesizes a comparative answer with explicit attribution per source.

**Critical problems**:
- False equivalence when books use different notation for the same concept
- Asymmetric coverage must be surfaced, not hidden
- Vocabulary mismatch between ML (ISLP) and econometrics (Hansen) terminology requires a concept-mapping layer

---

### 3. Figure-Aware Answers
**Architecture**: Single agent, dual-collection retrieval

Runs parallel retrieval over the text collection and the image caption collection. A relevance scorer gates which figures are actually worth including. The assembler always retrieves the section a figure belongs to as mandatory context.

**Critical problems**:
- Figure retrieval quality is bounded by caption quality from ingestion
- Decision gate needed on whether to call a vision model (expensive) or use only the caption (cheaper)
- Figures shown without their explanatory section context are often misleading

---

### 4. Exercise / Self-Quiz Generator
**Architecture**: Single agent, two-stage chain

Stage 1 generates N questions with difficulty tags from the retrieved section. Stage 2 generates answer rubrics and hints per question. A quiz store persists results to enable spaced repetition logic across sessions.

**Critical problems**:
- Self-check pass required: can the question actually be answered from the retrieved text?
- Repetition tracking across sessions is necessary or popular sections generate the same questions repeatedly
- LaTeX in generated questions requires a rendering layer (KaTeX / MathJax) from day one

---

### 5. Semantic Navigator
**Architecture**: Single agent, retrieval-only

Minimal generation. Query is expanded with domain synonyms and statistical vocabulary before retrieval. Results are returned as structured location references (book, chapter, section, approximate page) rather than prose answers.

**Critical problems**:
- Vocabulary gap between user language and book language is the core challenge; query expansion is not optional
- Response format must distinguish retrieval intent (get the answer) from navigation intent (find where to read)
- Concepts appearing across many sections require a canonical ranking heuristic beyond cosine similarity

---

### 6. Concept Graph / Prerequisite Tracer
**Architecture**: Multi-agent

Three agents under an orchestrator: a Retriever Agent that pulls the target section and all sections it references; a Graph Builder Agent that extracts concept dependencies and constructs a directed acyclic graph; and a Sequencer Agent that orders prerequisites into a readable learning path.

**Critical problems**:
- Implicit dependencies (inferred from vocabulary, not stated) are error-prone to extract
- LLM-generated graphs regularly contain cycles; cycle detection and breaking heuristics are required
- Prerequisites may cross book boundaries, requiring a unified section ID namespace

---

### 7. Annotated Reading Mode
**Architecture**: Single agent, batch retrieval

Extracts technical terms from user-pasted text, runs one retrieval per term in parallel, pairs each term with the best matching section, and generates inline annotations in a glossary style.

**Critical problems**:
- Noun phrase extraction is non-trivial for mathematical text
- Annotation density needs a relevance threshold and a depth setting to avoid overwhelming the user
- Terms not covered by either book must return a graceful "not in library" response, never a hallucinated annotation

---

### 8. Research Assistant Mode
**Architecture**: Multi-agent

An Orchestrator routes to three agents: a Claim Extractor that breaks the paper excerpt into atomic claims; a Retriever that finds the most relevant chunks per claim; and a Stance Classifier that labels each claim-chunk pair as SUPPORTS, CONTRADICTS, or PROVIDES BACKGROUND. A Synthesis Agent assembles the final annotated report.

**Critical problems**:
- Claim granularity is a hard problem — wrong granularity loses meaning
- SUPPORTS vs. PROVIDES BACKGROUND is a subtle distinction LLMs frequently get wrong
- Books are textbooks; papers are frontier research. Coverage gaps must be surfaced explicitly

---

### 9. Multi-Modal Math Explainer
**Architecture**: Single agent, vision-augmented

Retrieves both text sections (with LaTeX extracted) and relevant figures. A decision gate determines whether actual image bytes need to be sent to a vision model or whether the caption is sufficient. Output is rendered with KaTeX/MathJax + inline figures.

**Critical problems**:
- OCR errors in LaTeX from ingestion propagate into broken rendered equations
- Vision model calls are expensive and require a meaningful relevance gate
- Equations and their explanatory figures often live in different sections and must be retrieved together

---

### 10. Personalized Study Path Builder
**Architecture**: Multi-agent (most complex standard service)

A Goal Decomposer breaks the user's learning objective into sub-objectives. A Prereq Tracer (invoking Service 6) maps dependencies. A Sequencer orders sections into a progressive curriculum. A Path Generator produces the final weekly plan. A Progress Tracker store persists state and triggers re-planning when the user deviates.

**Critical problems**:
- Goal calibration is essential before path generation — vague goals produce wrong paths
- Coverage gaps in the two-book corpus must be detected and reported, not silently ignored
- Fixed linear paths break quickly; re-planning logic is as important as initial planning

---

### 11. Video Roadmap Generator
**Architecture**: Single agent (v1) → Multi-agent (v2)

**v1**: Multi-query retrieval decomposed by sub-topic → LLM generates a structured YAML production brief (scenes, concepts, sources, figure references, animation hints, duration estimates) → validator checks coverage and coherence.

**v2**: Three agents — a Retriever Agent producing an evidence pack, a Curriculum Agent sequencing concepts with prerequisite awareness, and a Production Agent translating the sequence into Remotion/Manim scene vocabulary.

Example output schema:
```yaml
topic: "Bias-Variance Tradeoff"
scenes:
  - id: 1
    title: "The prediction error problem"
    concept: "Why models fail on new data"
    source: { book: islp, chapter: ch02, section: "2.2" }
    suggested_visual: "animated scatter plot, overfitting curve"
    duration_hint: "90s"
  - id: 2
    title: "Decomposing the error"
    concept: "Bias² + Variance + Irreducible noise"
    source: { book: islp, chapter: ch02, section: "2.2.2" }
    figure: "fig_2_12_bias_variance_curve.png"
    suggested_visual: "manim: equation decomposition + curve animation"
    duration_hint: "2min"
```

**Critical problems**:
- Abstraction gap between user idea and a filmable production brief requires significant inference
- Production Agent needs a structured vocabulary of Remotion/Manim primitives to generate useful output
- Duration estimates require grounding in historical video data (concept type → typical duration)
- Retrieval scope creep: broad topics return 40+ sections; exclusion logic is harder than inclusion logic

---

## Agent Complexity Summary

| Service | Architecture | Hardest problem |
|---|---|---|
| 1. Tutor | Single + memory | Context window management |
| 2. Cross-book | Single, dual retrieval | Vocabulary mismatch |
| 3. Figure-aware | Single, dual collection | Caption quality gate |
| 4. Quiz | Single, 2-stage chain | Question validity |
| 5. Navigator | Single, retrieval-only | Query vocabulary gap |
| 6. Prereq tracer | **Multi-agent** | DAG cycle detection |
| 7. Annotated reading | Single, batch retrieval | Term extraction quality |
| 8. Research assistant | **Multi-agent** | Stance classification errors |
| 9. Math explainer | Single, vision-augmented | LaTeX fidelity + vision cost |
| 10. Study path | **Multi-agent** (complex) | Goal ambiguity + coverage gaps |
| 11. Roadmap | Single → **Multi-agent** | Visual primitive vocabulary |

Services 6, 8, and 10 require multi-agent design from day one. All others can be shipped as single-agent and promoted to multi-agent if quality demands it.

---

## Implementation Principles

**Start simple, promote when quality breaks.** Ship every service as the simplest architecture that could work. Add agents only when you can measure that single-agent quality is insufficient for a specific failure mode.

**Modal switching is free.** Same retrieval backbone, same Qdrant instance, same embedding model — switching modes is a prompt swap and output schema change, not a new system.

**Source attribution is non-negotiable.** Statistical content has precise definitions. Every answer must cite the book, chapter, and section it draws from. Hallucination without citation is harder to catch in this domain.

**Image quality gates are required.** The image collection is only as useful as its captions. Any service that touches figures must have an explicit relevance threshold before injecting them into answers or context.

**The roadmap generator is the most distinctive service.** No generic RAG system produces video production briefs. This is the highest-leverage differentiator and should be prioritized after the tutor and navigator are stable.

---

*Document generated from brainstorming session. Stack: Qdrant 1.12.4 · text-embedding-3-large · GPT / DeepSeek · Python 3.12*