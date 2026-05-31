# Chat service — operational doc

SSE-streaming conversational layer over the hybrid retrieval pipeline. Lives at `src/services/chat/`. Imports only `src.core.*`. Front-end SPA lives at `web/` (React + Vite + TS).

## Per-feature deep-dive

See [`docs/services/chat-features/`](./chat-features/README.md) — 35 docs (one per feature) with code snippets, mermaid flow graphs, tests, and trade-offs.

## Quick start

Pre-reqs: `.env` with `OPENAI_API_KEY` (optional `DEEPSEEK_API_KEY`).

### Option A — host dev mode (recommended for active work)

Lowest-friction, hot reload, no rebuilds:

```bash
docker compose -f ops/docker/docker-compose.yml up -d           # Qdrant only (default profile)
.venv/bin/python -m pip install -r requirements.txt             # one-time
(cd web && npm install)                                         # one-time
./scripts/dev.sh                                                # backend :8766 + frontend :5175
```

Open <http://localhost:5175>. Vite proxies `/api/*` to the local FastAPI on `:8766`.

**Deep links** — every conversation has a permalink in the form
`http://localhost:5175/c/<conversationId>`. Opening the URL auto-loads the
conversation; clicking a sidebar entry pushes the path so back/forward and
bookmarks work. The hash form `/#/c/<conversationId>` is also accepted.
Append `#cite-<N>` to deep-link directly to a citation card — the Sources
panel auto-opens and the page scrolls to the matching `[N]` entry.

**Delete conversations** — hover a sidebar row to reveal an `×` button.
Click → confirm → the conversation row + all messages are removed from
`data/chat.db` via `DELETE /api/conversations/{id}`. The deleted-active
case clears the URL back to `/`.

**Export to Zip (Markdown + images)** — two granularities, both pure frontend
(no backend route; the transcript already lives in the client store). The
Topbar download icon (left of the theme toggle) exports the **active
conversation**; a small download icon at the end of each completed answer
exports **that single answer**. Both download a **`.zip`** containing the
Markdown plus every referenced figure image, fetched from same-origin
`/api/figures…`, deduped (each image stored once even if cited twice), with the
Markdown's image links rewritten to relative `images/<name>` paths so it renders
offline in any viewer. Filenames: `statrag-<slug>.zip` /
`statrag-<slug>-a<NN>.zip`; zip layout `<doc>.md` + `images/`.

Serialization lives in `web/src/lib/exportMarkdown.ts` + `exportStructured.ts`
(block prose → `$$math$$`, figures, source chips; faithful per-schema layout for
`TutorAnswer` — with a `json` fence fallback for any future schema). Bundling
lives in `web/src/lib/exportZip.ts` (`extractImageUrls` + `buildZipBlob`, uses
`jszip`). In-flight/errored turns are skipped from full exports; images that
fail to fetch keep their original link and are simply not bundled.

### Option B — full Docker stack (prod profile)

For production-style runs, container builds, or smoke testing the prod image:

```bash
docker compose -f ops/docker/docker-compose.yml --profile prod up -d --build
```

Services: `qdrant` :6333, `statrag-chat` :8765, `statrag-web` :5173, `qdrant-backup` (oneshot snapshot on every up, keeps last 3 per collection — see [`ops/docker/README.md`](../../ops/docker/README.md)).

Open <http://localhost:5173>.

The dev (`:8766`/`:5175`) and prod (`:8765`/`:5173`) ports are intentionally different so the two can coexist without conflicts.

## Architecture

```
Browser SPA (React 18)
        │  fetch + ReadableStream (SSE)
        ▼
FastAPI app — src/services/chat/api.py
  ├─ /api/books         ← books.py        (registry from manifest + yamls)
  ├─ /api/search        ← retrieval.py    (hybrid RRF over per-field collections)
  ├─ /api/models        ← llm/router.py   (OpenAI + DeepSeek + Groq providers)
  ├─ /api/conversations ← store.py        (SQLite at data/chat.db)
  ├─ /api/preferences   ← store.py
  └─ /api/chat (SSE)    ← orchestrator.py (rewrite → retrieve → LLM stream → emit events)
        │
        ▼
src/core/qdrant_store.py  →  Qdrant (per-field collections)
src/core/config.py        →  .env (keys, models, host/port)
```

## Endpoints

| Method | Path | Body / params | Returns |
|---|---|---|---|
| GET  | `/api/health` | — | `{status: "ok"}` |
| GET  | `/api/books` | — | `Book[]` (26 indexed) |
| GET  | `/api/books/{slug}` | — | `Book` or 404 |
| POST | `/api/search` | `SearchRequest` | `{sources, figures, metadata}` |
| GET  | `/api/models` | — | `ModelProvider[]` |
| GET  | `/api/conversations` | — | `ConversationDigest[]` |
| POST | `/api/conversations` | `{title, mode, model_id, book_filter}` | digest |
| GET  | `/api/conversations/{id}` | — | digest + messages |
| DELETE | `/api/conversations/{id}` | — | 204/404 |
| GET  | `/api/preferences` | — | dict |
| PATCH | `/api/preferences` | dict | dict |
| POST | `/api/chat` | `ChatRequest` | SSE stream |
| GET  | `/api/chat/{conv_id}/stream` | `?after=<seq>` | SSE stream (resume/replay) |
| GET  | `/api/chat/{conv_id}/status` | — | `{exists, active, done, seq}` |

SSE event types (in order of arrival, approximate): `meta`, `token` (many), `paragraph_break`, `math_block`, `figure`, `source_chip`, `sources_full`, `figures_full`, `figures_meta`, `retrieval_meta`, `usage`, `structured_output`, `done`. On failure: `error` then `done`. Every event carries a monotonic `seq` (1-based) and the SSE `id:` field. `usage` carries running token counts for the stats pill (see [feature 30](./chat-features/30-stats-pill.md)). `figures_meta` carries `{status, reason, candidateCount, approvedCount}` for the image branch — frontend surfaces `no_candidates` / `all_rejected` / `error` as a chip in the figures panel (see [feature 40](./chat-features/40-image-only-ingest.md)).

### Detached, resumable runs (§13)

A `POST /api/chat` **with** a `conversationId` no longer streams the generator directly: it starts a *detached run* (`runs.py`) — a background `asyncio.Task` that drains the generator into a per-conversation event buffer and fans out to subscriber connections. The HTTP connection is just a subscriber, so disconnecting (switching conversation, refresh, tab-close, network drop) does **not** cancel generation, and the assistant row is still persisted on completion. A `POST` without a `conversationId` keeps the legacy connection-bound stream (ephemeral, not persisted).

- **Resume**: `GET /api/chat/{conv_id}/stream?after=<seq>` replays buffered events with `seq > after`, then streams live to `done`. The frontend uses this after a reload (or when reopening a conv whose local stream was lost), replaying from `after=0` into a fresh assistant placeholder.
- **Handshake**: `GET /api/chat/{conv_id}/status` → `{exists, active, done, seq}`. The frontend calls it once on open; if `active`, it attaches a resume stream.
- **Lifecycle**: at most one *active* run per conversation (a duplicate `POST` attaches to the running one). A finished run is retained `RUN_TTL_SECONDS` (300s) for late subscribers, then GC'd. Runs are process-local — a backend restart loses an in-flight run (persisted turns survive).
- **Frontend**: `web/src/state/chat.ts` holds a multi-conversation store (`byConv` keyed by convId, plus `active`); switching conversations no longer aborts the in-flight `fetch`. The sidebar shows a pulsing dot on conversations whose run is still streaming.

## Configuration

Read by `src.core.config.settings` from `.env`:

| Env var | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | (required) | OpenAI streaming |
| `DEEPSEEK_API_KEY` | "" | DeepSeek streaming (lazy, only when picked) |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek OpenAI-compat endpoint |
| `GROQ_API_KEY` | "" | Groq streaming (lazy, only when picked) |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Groq OpenAI-compat endpoint |
| `GROQ_DEFAULT_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq default |
| `EMBEDDING_MODEL` | `text-embedding-3-large` | dense embeddings |
| `OPENAI_MODEL_NANO` | `gpt-5.4-nano-2026-03-17` | default cheap |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | DeepSeek default |
| `QDRANT_HOST`/`QDRANT_PORT` | localhost/6333 | Qdrant |

Frontend reads no env directly — `/api` is proxied to `:8000` by Vite (see `web/vite.config.ts`).

## Models

Hardcoded in `src/services/chat/llm/router.py`:

- OpenAI: `gpt-4o`, `gpt-4o-mini`, `gpt-5.4-nano-2026-03-17` (default), `gpt-5.4-2026-03-05`.
- DeepSeek: `deepseek-chat`, `deepseek-reasoner`, `deepseek-v4-pro`.
- Groq: `meta-llama/llama-4-scout-17b-16e-instruct` (Groq default), `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`.

Routing: IDs starting with `deepseek*` → DeepSeek client; IDs in the explicit `GROQ_MODEL_IDS` set → Groq client (membership, not prefix — `openai/gpt-oss-*` collides with the OpenAI provider's prefix); else OpenAI client. All three clients use the `openai` SDK (DeepSeek + Groq via `base_url`). Groq's native `response_format` is trusted (no nano coercion). See invariant #26.

## Collections mapping (demo ↔ reality)

The reference demo at `docs/upgrades/Demo/ChatSystem/` assumed per-BOOK collections (`islp_chunks`, `hansen_chunks`). Reality is per-FIELD (`introduction_textbooks`, `econometrics_textbooks`, …) with a `book_slug` payload key. `books.collections_for_books(slugs)` groups requested books by field and emits payload filters `book_slug IN [...]`. The frontend never touches collection names.

## Persistence

`data/chat.db` (SQLite, WAL). Tables: `conversations`, `messages`, `prefs`. Schema in `src/services/chat/store.py`. Lazy init via `init_db()` on first write.

## Tests

```bash
.venv/bin/python -m pytest src/services/chat/tests/ -v
```

Coverage: BookRegistry (8), retrieval + highlights (17), LLM router (9), store (13), SSE orchestrator (14) = 61 tests.

## Streaming protocol details

See `docs/upgrades/Demo/ChatSystem/design_handoff_statrag/05_rag_pipeline.md` for exact event payloads. The orchestrator implements the heuristic-highlight path: spans are computed at retrieval time (sentence-level dense re-score) rather than via LLM tool calls.

## Chinese-wall check

```bash
grep -rE "from src\.(ingestion|services\.(retrieval|eval))" src/services/chat/ && echo "WALL VIOLATION" || echo "wall ok"
```

Should print `wall ok`.

## Chat modes

| Mode id | Description | Feature doc |
|---|---|---|
| `tutor` | Deep multi-aspect learning — synthesis plan, orchestrator-workers, author-diversity, coverage check, figure judge | [36-deep-tutor.md](./chat-features/36-deep-tutor.md) |
| `qa` | Punctual Q&A — 4-node scope→retrieve→generate→verify pipeline, lean `QAAnswer` schema, gpt-5.4-nano default | [51-qa-mode.md](./chat-features/51-qa-mode.md) |
| `facilitate` | Structural chapter traversal — teach sections in chapter reading order, building prior context across sections | [52-chapter-modes.md](./chat-features/52-chapter-modes.md) |
| `resume` | Structural chapter traversal — compress sections in chapter reading order into dense summaries | [52-chapter-modes.md](./chat-features/52-chapter-modes.md) |

### Q&A mode

The `qa` mode answers a single specific doubt punctually instead of teaching a topic globally. It runs a lean 4-node pipeline (scope-extract → hybrid retrieve → scoped generate → grounding verify), emits a `QAAnswer` with an inline scope line and a grounding-confidence badge, and defaults all LLM nodes to `gpt-5.4-nano`. On a corpus miss (0 retrieved sources) it emits an honest no-coverage message with empty citations rather than fabricating an answer. See [`chat-features/51-qa-mode.md`](./chat-features/51-qa-mode.md) for the full pipeline spec, env flags, and synced-artifacts checklist.

### Chapter modes (facilitate / resume)

The `facilitate` and `resume` modes traverse a chapter's sections in **structural reading order** (`page_from`, then `section_id`) rather than by search relevance. `facilitate` teaches each selected section in sequence, threading prior-context forward so each block can reference what was covered before. `resume` compresses the same span into dense per-section summaries. Both modes are scoped to named subtopics within a single book+chapter; an empty subtopic list spans the whole chapter. Blocks in the emitted `ChapterDigest` are in fetched-section order and are **never re-sorted downstream** — this is an enforced invariant. See [`chat-features/52-chapter-modes.md`](./chat-features/52-chapter-modes.md) for the full pipeline spec (parse-scope → fetch-chapter → resolve-subtopics → map → stitch → ground), env flags, and synced-artifacts checklist.

## Status (2026-05-19)

- Backend: 14 routes + `GET /api/figures` (whitelisted figure serving), 488 tests pass, SSE verified end-to-end via curl across 6 fields.
- Image library: 25/25 yaml books indexed across all 6 `<field>_images` collections (8083 total points, 30× growth from 271). Pipeline at [feature 40](./chat-features/40-image-only-ingest.md).
- Deep tutor pipeline ([feature 36](./chat-features/36-deep-tutor.md), [39](./chat-features/39-image-judge.md)) now:
  - Injects approved figures inline in the aspect markdown (lead → image → caption-based explanation) via overlap-scored aspect placement (TL;DR excluded).
  - Pre/post-repairs LaTeX backslash escapes that the LLM mangles inside JSON (`\theta` → tab+`heta` → repaired back to `\theta`).
  - Wraps bare-LaTeX math runs in `$..$` so KaTeX activates even when the model forgets delimiters.
- TutorView:
  - TL;DR section auto-expands; other sections collapse-on-render with a `max-height + opacity` animation (220 ms ease-out enter, ease-in exit, `prefers-reduced-motion` honoured).
  - `[F<n>]` / `[Figure <n>]` / `[Image #<n>]` rendered as clickable figure pills (`#fig-N`) that auto-open all collapsed sections.
  - Inline `<figure>` rendering + bullet/numbered list parsing.
- Frontend: scaffold + shell + chat UI + SSE client + modals compiled (tsc clean). Earlier polish wave (features [30-35](./chat-features/README.md)): stats pill, streaming motion, Config button, sidebar conversation loading, real figure image previews, strict-red dark mode.
- Dev ports: backend `:8766`, Vite `:5175` (proxy `/api` -> `:8766`). Override backend via `STATRAG_BACKEND_PORT`.
- Prod-profile ports (Docker): backend `:8765`, Vite `:5173`.

## Next step — make chat work in browser

Backend pipes data; UI compiled. **Next milestone = verify and harden the in-browser chat loop end-to-end.** Open priorities:

1. **Browser smoke test** — open `http://localhost:5173`, send a tutor-mode query, verify:
   - SSE events render incrementally (token-by-token fade-in)
   - KaTeX math blocks render (not raw `$$...$$`)
   - Source chips clickable → `SourceModal` opens with highlighted spans
   - ContextPanel populates with sources/figures/retrieval metadata
   - BookModal opens on `⌘B`, toggles persist
   - Model selection is per-pipeline-stage via the About-Tutor modal diagram (the toolbar Model + CONFIG buttons were removed; see chat-features/41-about-model.md)
2. **Fix whatever breaks** — first browser pass will surface real bugs (paragraph_break boundaries, math escaping, chip ordering, source-modal highlight ranges, reducer state edge cases). Iterate on `web/src/state/chat.ts` + `components/MessageThread.tsx`.
3. **Conversation persistence** — frontend currently does not call `POST /api/conversations` before streaming; messages are not saved. Wire conversation create on first send + pass `conversationId` to subsequent `/api/chat` calls.
4. **Status dot wiring** — periodic `GET /api/health` (every 10s) → toggle `is-online` class on `.status-dot`.
5. **Error UX** — render `error` SSE event as the red retry strip from `03_interactions.md`.
6. **Streaming polish** — debounce token batches to avoid layout thrash; ensure auto-scroll only when user is at bottom.

After those, Part 2 v1 ready. Beyond:

- LLM-cited highlight ranges (replace heuristic)
- Mode output views for additional modes (when re-introduced)
- Job progress modal for indexing new books
- Real cover imagery + figure thumbnails (Manim/matplotlib renders)
- Auth + multi-tenant
- Production build: `npm run build` → `web/dist/` served via FastAPI `StaticFiles` or nginx

## Troubleshooting

- **No tokens streaming**: check `OPENAI_API_KEY` env or `.env`. SSE `error` event will carry `LLMError` message.
- **`/api/books` empty**: missing `data/parsed/manifest.json` or `src/ingestion/books/*.yaml`.
- **Vite proxy buffers SSE**: already set `X-Accel-Buffering: no` + `cache-control: no-transform`. If running behind nginx, mirror those headers.
- **Qdrant offline**: `/api/search` and `/api/chat` will surface `ConnectionError`. Status dot in UI goes grey on `/api/health` failure (TODO: wire periodic ping).
