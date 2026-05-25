# 19 — SSE orchestrator

## Purpose

Central pipeline that ties every other module together. Streams typed events over SSE. Branches early on `ModeSpec.arch == "multi"` for prereqs/research/path; otherwise the single-agent loop: rewrite → expand → retrieve → rerank → memory → LLM stream → tokenize → validate → emit sources/figures/metadata → done.

## Event sequence

```
meta → token* / paragraph_break* / math_block* → [structured_output] → source_chip*
     → sources_full → [figures_full] → retrieval_meta → done
                                                       (error + done on failure)
```

## Flow

```mermaid
graph TD
  Req["ChatRequest{conversationId, message, mode, model, bookFilter}"] --> Mode["ModeRegistry.get(mode)"]
  Mode --> Arch{spec.arch}
  Arch -->|multi| Multi["dispatch to agents.prereqs/research/study_path"]
  Multi --> SO["yield structured_output{schema, data}"]
  SO --> Done
  Arch -->|single| RW["rewriter.rewrite_query"]
  RW --> EXP["query_expansion.expand_queries(flags)"]
  EXP --> NQ{len(queries)>1?}
  NQ -->|yes| MQ["multi_query_hybrid_search (parallel)"]
  NQ -->|no| HS["hybrid_search single"]
  MQ & HS --> HL["compute_highlights per source"]
  HL --> Fig{vision mode?}
  Fig -->|yes| VG["vision_gate -> inspect_figure"]
  Fig -->|no| SF["search_figures"]
  VG & SF --> Meta["yield meta{books, sourceCount, latencyMs, model}"]
  Meta --> Build["build LLM messages: system_prompt + memory + history + user"]
  Build --> LLM["llm.stream(messages, model)"]
  LLM --> Proc["_process_stream: split on \\n\\n and $$...$$"]
  Proc --> Emit["yield token / paragraph_break / math_block"]
  Emit --> Acc[accumulate text]
  Acc --> Valid{output_schema != TutorAnswer?}
  Valid -->|yes| VR["_validate_and_repair (1 retry on fail)"]
  VR --> SO2[yield structured_output]
  Valid -->|no| Skip
  SO2 & Skip --> Chips["yield source_chip per source"]
  Chips --> Full["yield sources_full + figures_full + retrieval_meta"]
  Full --> Idx["index_turn (if memory vec/persist)"]
  Idx --> Done["yield done"]
```

## Key code

`src/services/chat/orchestrator.py`:

```python
async def stream_chat(req: ChatRequest, history: list[dict] | None = None
                      ) -> AsyncIterator[dict]:
    """SSE pipeline. Yields event dicts."""
    t0 = time.time()
    try:
        spec = ModeRegistry.get(req.mode)

        # Multi-agent dispatch
        if spec.arch == "multi":
            yield {"type": "meta", "mode": req.mode, ...}
            if req.mode == "prereqs":
                from src.services.chat.agents.prereqs import run_prereqs
                dag = await run_prereqs(req.message, book_slugs)
                yield {"type": "structured_output", "schema": "DAG",
                       "data": dag.model_dump()}
            elif req.mode == "research":
                from src.services.chat.agents.research import run_research
                rep = await run_research(req.message, book_slugs)
                yield {"type": "structured_output", "schema": "Report",
                       "data": rep.model_dump()}
            elif req.mode == "path":
                from src.services.chat.agents.study_path import run_study_path
                prev = store.get_study_plan(req.conversationId) if req.conversationId else None
                version = (prev["version"] if prev else 0) + 1
                plan = await run_study_path(req.message, book_slugs,
                                             replanned_from_version=prev["version"] if prev else 0)
                if req.conversationId:
                    store.upsert_study_plan(req.conversationId, plan.model_dump(),
                                             version=version)
                yield {"type": "structured_output", "schema": "StudyPlan",
                       "data": plan.model_dump()}
            yield {"type": "done"}
            return

        # Single-agent path
        rewritten = rewrite_query(req.message, history)
        flags = spec.retrieval_flags
        book_slugs = None if req.bookFilter in ("ALL", []) else list(req.bookFilter)
        queries = await expand_queries(rewritten, flags=flags)
        if len(queries) > 1:
            sources, metadata = await multi_query_hybrid_search(
                queries, book_slugs=book_slugs, top_k=5,
                rerank=flags.rerank, rerank_top_n=flags.rerank_top_n,
            )
        else:
            sources, metadata = hybrid_search(
                rewritten, book_slugs=book_slugs, top_k=5,
                rerank=flags.rerank, rerank_top_n=flags.rerank_top_n,
            )

        # Highlights
        for src in sources:
            try:
                src.highlights = compute_highlights(req.message, src.chunk, max_spans=2)
            except Exception: pass

        # Figures (vision-aware for figures/math modes)
        figures = []
        if spec.model == "pro_vision" and req.mode in ("figures", "math"):
            # ... vision_gate + inspect_figure (see doc 14)
        else:
            figures = search_figures(rewritten, book_slugs, k=2)

        yield {"type": "meta", "mode": req.mode, "books": [s.book for s in sources],
               "sourceCount": len(sources), "latencyMs": int((time.time()-t0)*1000),
               "model": req.model}

        # Build messages
        system_text = spec.system_prompt + ... + append_sources(sources)
        messages = [ChatMessage(role="system", content=system_text)]
        if spec.memory != "off" and req.conversationId:
            mem_msgs = await build_memory_context(req.conversationId, req.message,
                                                   strategy=spec.memory, history=history)
            messages.extend(mem_msgs)
        if history:
            for msg in history:
                if msg["role"] in ("user", "assistant") and isinstance(msg["content"], str):
                    messages.append(ChatMessage(msg["role"], msg["content"]))
        messages.append(ChatMessage("user", req.message))

        llm, model_id = get_llm(req.model)
        accumulated = []
        async for ev in _process_stream(llm.stream(messages, model=model_id)):
            if ev["type"] == "token":
                accumulated.append(ev["text"])
            yield ev

        full_text = "".join(accumulated)

        # Schema validate + repair (if non-tutor mode)
        if spec.output_schema is not TutorAnswer:
            data, err = await _validate_and_repair(full_text, spec, llm, model_id)
            if data:
                yield {"type": "structured_output",
                       "schema": spec.output_schema.__name__, "data": data}
            else:
                yield {"type": "error", "code": "SCHEMA_REPAIR_FAILED", "message": err}

        # Source chips inline
        for s in sources:
            section_label = f"{s.chapter} {s.section}".strip() if s.chapter else s.section
            yield {"type": "source_chip", "book": s.book, "section": section_label}

        yield {"type": "sources_full", "sources": [s.model_dump() for s in sources]}
        if figures:
            yield {"type": "figures_full", "figures": [f.model_dump() for f in figures]}
        yield {"type": "retrieval_meta", "meta": metadata.model_dump()}

        # Index for vec memory
        if req.conversationId and spec.memory in ("vec", "persist", "auto"):
            n_turns = len(history) if history else 0
            if _resolve_strategy(spec.memory, n_turns + 2) in ("vec", "persist"):
                await index_turn(req.conversationId, "user", req.message, n_turns)
                await index_turn(req.conversationId, "assistant", full_text, n_turns + 1)

        yield {"type": "done"}

    except LLMError as exc:
        yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
        yield {"type": "done"}
    except Exception as exc:
        yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
        yield {"type": "done"}
```

## Token stream processor

```python
async def _process_stream(raw: AsyncIterator[str]) -> AsyncIterator[dict]:
    """Split LLM token stream into typed events.

    - \\n\\n → paragraph_break (after flushing prior tokens)
    - $$...$$ → math_block (when full block in buffer)
    """
    buf = ""
    state = _STATE_NORMAL
    async for chunk in raw:
        buf += chunk
        while True:
            if state == _STATE_NORMAL:
                para_pos = buf.find("\n\n"); math_pos = buf.find("$$")
                # ... pick nearest, flush prefix as token, emit break or enter math state
            else:  # _STATE_MATH
                close = buf.find("$$")
                if close == -1: break  # wait for more
                yield {"type": "math_block", "tex": buf[:close]}
                buf = buf[close + 2:]; state = _STATE_NORMAL
    # Final flush
    ...
```

## Heartbeat

`sse-starlette` `EventSourceResponse(event_gen(), ping=15)` — sends a comment line every 15s if no tokens, keeps connection alive through proxies.

## Tests

`test_sse.py` — 14 tests:
- meta event arrives first
- done arrives last
- token/paragraph_break/math_block ordering preserved
- LLMError → error + done sequence
- sources_full and retrieval_meta arrive before done
- TestFastAPIEndpoints: /api/health 200, /api/models nonempty
