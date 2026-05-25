# 04 — Data Model

TypeScript types covering every piece of state and data shown in the UI. These should match the backend's response shapes 1:1.

The prototype's data lives in `design/data.js` as plain JS objects — read it alongside this doc.

---

## Books / corpus

```ts
type BookId = 'ISLP' | 'HANSEN' | 'ESL' | 'WOOLDRIDGE' | string

interface Book {
  id: BookId                       // stable identifier used in source/chunk metadata
  title: string                    // "An Introduction to Statistical Learning"
  subtitle: string                 // "with Applications in Python"
  short: string                    // "ISLP" — what shows on chips/tags
  authors: string                  // "James, Witten, Hastie, Tibshirani, Taylor"
  authorsShort: string             // "James et al." — for tight spaces
  edition: string                  // "2nd ed. · Springer · 2023"
  chunks: number                   // count of indexed chunks
  figures: number                  // count of indexed figures
  chapters: number
  color: string                    // hex — used for dots, pins, glow tint
  cover: 'islp' | 'hansen' | 'esl' | 'wooldridge' | string   // which BookCover SVG to render
  description: string              // longer prose shown in BookCard
  collection: string               // Qdrant collection name, e.g. "islp_chunks"
  selected: boolean                // user's current include/exclude state
  indexed?: boolean                // default true; false = "not yet indexed"
}
```

In production:
- `chunks`, `figures`, `chapters` come from Qdrant collection stats (`GET /collections/{name}`).
- `selected` is a user preference (per user × per book), not a book property — split it off if you have a real user model.
- `cover` should ideally point to a real image URL. Until you have cover assets, keep the SVG-key approach.

---

## Conversations & threads

```ts
type ConversationId = string

interface Conversation {
  id: ConversationId
  title: string                    // auto-derived from first user message, user-editable
  mode: ModeId                     // last-used mode for this conversation
  createdAt: ISODateString
  updatedAt: ISODateString
  bookFilter: BookId[] | 'ALL'     // remember which collections were active
  modelId: string                  // remember which model was last used
}

interface ConversationDigest extends Conversation {
  active?: boolean                 // marker for the sidebar's currently-open conversation
}
```

For the sidebar grouping helper:

```ts
type ConversationGroups = {
  today:     ConversationDigest[]
  yesterday: ConversationDigest[]
  thisWeek:  ConversationDigest[]
  earlier:   ConversationDigest[]
}
```

Group on the server based on the user's timezone. Falling back to client grouping is fine for small lists.

### Thread (messages)

```ts
type Message = UserMessage | AssistantMessage

interface UserMessage {
  role: 'user'
  id: string
  time: string                     // "14:31" — formatted for display; keep ISO timestamp separately for sorting
  timestamp: ISODateString
  text: string                     // plain text, no markdown
  attachments?: Attachment[]       // for annotate / research modes
}

interface AssistantMessage {
  role: 'assistant'
  id: string
  time: string
  timestamp: ISODateString
  mode: ModeId                     // which mode produced this answer
  model: string                    // model id, e.g. "gpt-4o"
  books: BookId[]                  // which collections were queried
  sourceCount: number              // for the badge
  latencyMs: number                // time-to-first-meta or total, your call
  blocks: AssistantBlock[]         // ordered renderable units (see below)
  sources?: Source[]               // full retrieval results — drives ContextPanel
  figures?: Figure[]               // figure references — drives ContextPanel + inline cards
  retrievalMetadata?: RetrievalMetadata
  error?: { code: string; message: string }
}
```

### Assistant blocks

The body of an assistant message is **not** a single markdown string. It's an ordered array of typed blocks so the renderer can switch on `type`:

```ts
type AssistantBlock =
  | { type: 'p'; text: string }                          // sans paragraph; supports inline $math$ and **bold**
  | { type: 'math'; tex: string }                        // KaTeX display block
  | { type: 'figure'; ref: string; book: BookId; chapter: string; caption: string; chart: ChartKind | string /* url */ }
  | { type: 'sources'; chips: SourceChip[] }             // inline citation row

type SourceChip = {
  book: BookId
  section: string                  // "ch07 §7.4" — the chapter+section concatenated as shown in-text
}
```

Why blocks instead of markdown:
- Math blocks need KaTeX, not markdown's `$$`.
- Figures are first-class — they have a thumb, caption, click-to-lightbox.
- Source chips are interactive — they open `<SourceModal>`. Plain markdown can't.

If your backend produces markdown today, write a small parser that converts to this block shape. Keep markdown for the `text` inside paragraph blocks (bold + inline math + maybe links).

---

## Sources & figures

```ts
type Score = number              // 0..1 — cosine or hybrid score

interface Source {
  rank: number                   // 1-indexed
  book: BookId
  chapter: string                // "ch06"
  section: string                // "§6.2.1"  (no chapter prefix here — that's separate)
  title: string                  // "Ridge Regression"
  excerpt: string                // ~2 lines, used in the SourceCard; italic quoted
  score: Score
  page?: number
  chunkId: string                // stable identifier, e.g. "islp_ch06_p247_b3"
  embedding?: string             // "BAAI/bge-large-en-v1.5"
  chunk: string                  // full chunk text — shown in SourceModal
  highlights: string[] | HighlightRange[]   // see below
}

// Preferred — backend-provided character ranges
interface HighlightRange { start: number; end: number; reason?: string }

interface Figure {
  ref: string                    // "fig_6_4"
  book: BookId
  chapter: string
  caption: string
  chart: ChartKind | string      // either a built-in chart key or a thumbnail URL
}

type ChartKind = 'biasvar' | 'paths'   // built-ins in the prototype (replace with real renders)
```

**Highlights:** the prototype stores them as **substrings** of the chunk and uses indexOf-based matching. In production, **return character ranges from the backend** — substring matching is fragile (case, whitespace, post-processing all break it). Keep `string[]` as a fallback for legacy.

---

## Modes

```ts
type ModeId =
  | 'tutor' | 'compare' | 'figures' | 'quiz' | 'navigate'
  | 'prereqs' | 'annotate' | 'research' | 'math' | 'path' | 'roadmap'

interface ModeMeta {
  id: ModeId
  label: string                  // "Tutor"
  glyph: string                  // one-char fallback when no icon
  icon: string                   // key into the icon set
}
```

Only **Tutor** is fully designed. The other modes are pickable but have not had output views designed. Treat them as "future" — pick `tutor` by default.

---

## Models & providers

```ts
type ProviderId = 'openai' | 'deepseek'

interface ModelProvider {
  id: ProviderId
  name: string                   // "OpenAI"
  short: string                  // "OAI"
  color: string                  // hex
  models: Model[]
}

interface Model {
  id: string                     // "gpt-4o", "deepseek-v3", etc.
  name: string                   // display name
  tagline: string                // "Fast multimodal"
  cost: '$' | '$$' | '$$$' | '$$$$'
  speed: 'fast' | 'med' | 'slow'
  ctx: string                    // "128k" — context window for display
}
```

Default model: `gpt-4o`. User can change via the ModelPicker in the input bar.

---

## Retrieval metadata

```ts
interface RetrievalMetadata {
  rewrittenQuery: string         // post-rewrite query that hit Qdrant
  embedding: string              // model id, e.g. "BAAI/bge-large-en-v1.5"
  retrievalMs: number
  collections: string[]          // Qdrant collection names hit
  filter: string                 // human-readable filter description, e.g. "book ∈ {ISLP, HANSEN}"
  topK: number                   // e.g. 5
  scoreThreshold: number         // e.g. 0.60
  mode: string                   // human-readable: "hybrid (sparse 0.3 + dense 0.7)"
}
```

This drives the bottom accordion in the ContextPanel. Useful for debugging when answers go sideways.

---

## Roadmaps (sidebar list)

The Roadmap mode output is not yet designed, but the sidebar shows saved roadmaps:

```ts
interface RoadmapDigest {
  id: string
  title: string                  // "Bias-Variance Tradeoff"
  scenes: number
  date: string                   // "May 12" — display-formatted; keep ISO sep.
}
```

---

## Tweaks / user preferences

```ts
interface UserPreferences {
  theme: 'dark' | 'light'
  accent: string                 // hex — set by theme toggle + manual picker
  density: 'compact' | 'comfortable'
  userStyle: 'bubble' | 'document'   // user message rendering style
  fontPair: 'plex' | 'editorial' | 'spectral'
  sidebarOpen: boolean
  contextOpen: boolean
  defaultModel: string           // model id
  bookFilter: BookId[] | 'ALL'   // default include set
}
```

The theme toggle in the Topbar must set **both `theme` and `accent`** atomically so the accent matches the theme's natural palette (see `02_components.md`).

---

## SSE event shape (chat stream)

For `POST /chat`, the response is SSE. Each line is `event: <kind>\ndata: <json>\n\n`.

```ts
type ChatEvent =
  | { type: 'meta', mode: ModeId, books: BookId[], sourceCount: number, latencyMs: number, model: string }
  | { type: 'token', text: string }
  | { type: 'paragraph_break' }
  | { type: 'math_block', tex: string }
  | { type: 'figure', ref: string, book: BookId, chapter: string, caption: string, chart: string }
  | { type: 'source_chip', book: BookId, section: string }
  | { type: 'sources_full', sources: Source[] }
  | { type: 'figures_full', figures: Figure[] }
  | { type: 'retrieval_meta', meta: RetrievalMetadata }
  | { type: 'done' }
  | { type: 'error', code: string, message: string }
```

Order of arrival is **not** strictly defined except:
- `meta` arrives first.
- `done` arrives last (or `error`).
- `sources_full` and `retrieval_meta` typically arrive before `done`, since the assistant streams text **after** retrieval has happened.

The renderer reduces these to the `AssistantMessage` shape above incrementally.

---

## REST endpoints (suggested)

```
GET    /conversations                        → ConversationDigest[]
POST   /conversations                        → Conversation       (creates empty)
GET    /conversations/:id                    → Conversation & { messages: Message[] }
DELETE /conversations/:id

POST   /chat                                 → SSE stream of ChatEvent
  body: { conversationId, message, mode, model, bookFilter, attachments? }

POST   /search                               → { sources: Source[], figures: Figure[] }
  body: { query, books?, topK?, scoreThreshold? }

GET    /books                                → Book[]
PATCH  /books/:id                            → Book               (toggle selected)

GET    /books/:id/chunks/:chunkId            → { chunk, highlights, ... }   (for SourceModal "Open in reader")
GET    /books/:id/figures/:ref               → { url, caption, ... }        (for figure lightbox)

GET    /models                               → ModelProvider[]
GET    /preferences                          → UserPreferences
PATCH  /preferences                          → UserPreferences

# Future (modes):
POST   /quiz/generate                        → QuizCard[]
POST   /roadmap/generate                     → Roadmap
POST   /prereqs/trace                        → { nodes, edges }
```

---

Continue to → `05_rag_pipeline.md`
