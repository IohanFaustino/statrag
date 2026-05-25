# 29 — SSE protocol reference

## Wire format

sse-starlette encodes each event as:

```
event: <type>
data: <json payload>

```

Frames separated by `\r\n\r\n`. Client parser must accept BOTH `\r\n\r\n` and `\n\n` (different proxies normalize differently).

## Event types

| Type | Order | Payload | Purpose |
|---|---|---|---|
| `meta` | always first | `{type, mode, books[], sourceCount, latencyMs, model}` | latency to first event = retrieval time |
| `token` | streaming | `{type, text}` | append to current paragraph |
| `paragraph_break` | streaming | `{type}` | close current `p`, start new one |
| `math_block` | streaming | `{type, tex}` | KaTeX display block |
| `figure` | streaming | `{type, ref, book, chapter, caption, chart}` | inline figure card |
| `source_chip` | post-tokens | `{type, book, section}` | inline chip (one per source) |
| `structured_output` | post-tokens | `{type, schema, data}` | full Pydantic-validated object (M2/M5/M6/M7) |
| `sources_full` | near end | `{type, sources: Source[]}` | populates ContextPanel |
| `figures_full` | near end (optional) | `{type, figures: Figure[]}` | populates ContextPanel figures section |
| `retrieval_meta` | near end | `{type, meta: RetrievalMetadata}` | populates retrieval accordion |
| `done` | always last | `{type}` | client closes stream |
| `error` | on failure | `{type, code, message}` | followed by `done` |

## Typical sequences

### Tutor (single agent, prose)

```
meta → (token+ → paragraph_break?)* → math_block? → source_chip*
     → sources_full → figures_full? → retrieval_meta → done
```

### Multi-agent (prereqs, research, path)

```
meta → structured_output{schema, data} → done
```

(No token stream — full payload arrives in one event after the graph runs.)

### Schema-mode single agent (quiz, navigate, annotate, roadmap)

```
meta → token+ → structured_output{schema, data} → source_chip*
     → sources_full → retrieval_meta → done
```

LLM emits JSON; orchestrator validates + emits `structured_output`. UI's view component renders the data.

### Error

```
meta → token* → error{code, message} → done
```

OR (on early failure before meta):

```
error{code, message} → done
```

## Heartbeat

`EventSourceResponse(event_gen(), ping=15)` sends `: ping\n\n` every 15s. Frontend parser ignores comment-only frames (no `data:` line found).

## Frontend reducer mapping

| Event | Reducer effect |
|---|---|
| meta | fill `assistantMsg.{mode, model, books, sourceCount, latencyMs}` |
| token | `appendToken(msg.blocks, text)` |
| paragraph_break | push empty `p` (skipped if last is empty) |
| math_block | push `{type: "math", tex}` |
| figure | push `{type: "figure", ref, book, chapter, caption, chart}` |
| source_chip | append to last `sources` block or create one |
| structured_output | set `msg.structuredOutput = {schema, data}` |
| sources_full | `msg.sources = ev.sources` + `state.sources = ev.sources` |
| figures_full | `msg.figures` + `state.figures` |
| retrieval_meta | `msg.retrievalMetadata` + `state.metadata` |
| done | `msg.status = "complete"`, strip trailing empty `p` |
| error | `msg.status = "error"`, set `msg.error` |

## Curl smoke test

```bash
curl -sN -X POST http://localhost:8765/api/chat \
  -H 'content-type: application/json' \
  -d '{"message":"What is ridge regression?","mode":"tutor",
       "model":"gpt-5.4-nano-2026-03-17","bookFilter":"ALL"}' \
  --max-time 30 | head -40
```

## Trade-offs (ADR-005)

- Heuristic highlight path: client renders highlights from char ranges returned by `compute_highlights` at retrieval time.
- LLM-cited-highlights path: model emits `cite(chunk_id, char_start, char_end, reason)` tool calls during generation; aggregated into `sources_full.sources[].highlights` before emission. Deferred to v2 (more accurate, more expensive).
