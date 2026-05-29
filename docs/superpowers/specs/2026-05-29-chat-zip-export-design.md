# Chat Zip Export (Markdown + Images) — Design

**Date:** 2026-05-29
**Agent:** system_Agent (frontend-only; no backend, no pipeline)
**Status:** design, pending build
**Builds on:** `2026-05-29-chat-markdown-export-design.md` (the `.md` serializer already shipped on `feat/chat-md-export`).

## Goal

The existing download buttons (Topbar = active conversation, per-answer icon = single answer) now download **everything bundled as a `.zip`**: the Markdown plus every image it references, fetched and stored locally, with the Markdown's image links rewritten to relative paths so it renders offline in any viewer.

## Decisions (locked with user)

- **Same buttons, no new UI.** The two existing download buttons now produce a `.zip` (not a `.md`). One click, downloads everything.
- **Always `.zip`.** Even when there are no images, the button outputs a `.zip` (containing just the `.md`). Uniform output.
- **Both granularities.** Topbar (full conversation) and per-answer both bundle their own images.
- **Dedup images.** A given image URL is fetched and stored **once**, even if referenced multiple times; all references rewrite to the same relative path.
- **Missing images: keep link, skip file.** Any image that 404s / fails to fetch keeps its original URL inline in the Markdown; only successfully-fetched images are bundled. Export never fails on a missing image.
- **Dependency:** add `jszip` to `web/package.json`.

## Architecture

Frontend-only. The `.md` serializer (`exportMarkdown.ts` / `exportStructured.ts`) is unchanged and reused. One new module turns a Markdown string + its images into a zip Blob.

```
web/src/lib/exportMarkdown.ts   MODIFY — replace downloadMarkdown(filename, content)
                                 with generic downloadBlob(filename, blob)
web/src/lib/exportZip.ts        NEW — extractImageUrls + buildZipBlob (uses jszip)
web/src/lib/exportZip.test.ts   NEW — vitest
web/src/App.tsx                 MODIFY — handlers become async, always emit .zip
web/package.json                MODIFY — add jszip
```

The `.md`-only download is removed from the buttons; `downloadMarkdown` is deleted (its only call sites were the two App handlers). The serializers `conversationToMarkdown` / `assistantMessageToMarkdown` stay and feed the zip.

### Module: `exportZip.ts`

```ts
// Pure except buildZipBlob's fetch + JSZip use (both injectable / output-asserted).
export function extractImageUrls(md: string): string[];
export interface ZipResult { blob: Blob; missing: string[] }
export function buildZipBlob(
  markdown: string,
  opts: { docName: string },          // e.g. "define-variance" -> define-variance.md
  fetchFn?: typeof fetch,             // injectable for tests; defaults to window.fetch
): Promise<ZipResult>;
```

**`extractImageUrls`** — pure. Scans for Markdown image syntax `![alt](url)` and returns the unique `url`s (first-seen order) whose target is a bundleable image: starts with `/api/`, `/img/`, `http://`, or `https://`. Ignores non-image links `[text](url)` and data URIs.

**`buildZipBlob`** — for each unique URL:
1. `fetchFn(url)`; if not `ok`, push to `missing[]`, leave the URL in the Markdown untouched.
2. On success: read `blob()`, derive a filename `images/<base>-<hash>.<ext>` (base = sanitized last path segment or "figure"; ext from content-type or URL; `<hash>` = short hash of the URL to avoid collisions between different URLs with the same basename), add to JSZip, and record `url -> images/<name>` for rewrite.
3. After all fetches: rewrite every recorded URL occurrence in the Markdown to its relative path (global replace, exact-URL match).
4. Add `<docName>.md` (rewritten) to the zip root. Generate the blob (`type: "application/zip"`).
5. Return `{ blob, missing }`. (`missing` is currently informational; not surfaced in UI per "keep link, skip file".)

Dedup is inherent: the URL set is unique, each fetched once, each rewritten everywhere.

### Module: `exportMarkdown.ts` change

Replace:
```ts
export function downloadMarkdown(filename: string, content: string): void
```
with:
```ts
export function downloadBlob(filename: string, blob: Blob): void
```
Same best-effort try/catch + `console.warn` pattern (mirrors `persist.ts`); Blob → object URL → anchor click → revoke. Markdown callers wrap their string in `new Blob([md], {type:"text/markdown"})` — but since buttons now always zip, the only caller is `buildZipBlob`'s consumer in App.

### App.tsx wiring (handlers become async)

```ts
const handleExportConversation = useCallback(async () => {
  if (messages.length === 0) return;
  const title = activeConvTitle.replace(/\s+/g, " ").trim();
  const slug = slugify(title);
  const md = conversationToMarkdown(messages, { title });
  const { blob } = await buildZipBlob(md, { docName: slug });
  downloadBlob(`statrag-${slug}.zip`, blob);
}, [messages, activeConvTitle]);

const handleExportMessage = useCallback(async (idx: number) => {
  const msg = messages[idx];
  if (!msg || msg.role !== "assistant") return;
  const title = activeConvTitle.replace(/\s+/g, " ").trim();
  const slug = slugify(title);
  let n = 0;
  for (let i = 0; i <= idx; i++) if (messages[i].role === "assistant") n++;
  const nn = String(n).padStart(2, "0");
  const md = assistantMessageToMarkdown(msg);
  const { blob } = await buildZipBlob(md, { docName: `${slug}-a${nn}` });
  downloadBlob(`statrag-${slug}-a${nn}.zip`, blob);
}, [messages, activeConvTitle]);
```

A brief async wait while images fetch. (Optional future: a spinner; out of scope now — fetches are fast and same-origin.)

## Zip layout

```
statrag-define-variance.zip
├── define-variance.md          (image links → images/…)
└── images/
    ├── image_rsrcD3S-1a2b.jpg
    └── image_rsrcD3R-9c4d.jpg
```

## Data flow

```
Click export
  → App: serialize messages → markdown (existing pure serializer)
  → buildZipBlob: extract image URLs → fetch each (dedup) → add to zip → rewrite links → md into zip
  → downloadBlob(.zip)
  → browser saves .zip
```

No backend route. Images fetched from same-origin `/api/figures?path=…` (dev server already serves them).

## Error handling

- Per-image fetch failure → keep original URL, skip file, record in `missing[]`. Never throws.
- JSZip generate failure → caught in `downloadBlob`/handler, `console.warn`; no crash.
- Empty conversation → Topbar button already disabled.

## Testing

**vitest** (`exportZip.test.ts`):
- `extractImageUrls`: dedupes repeated URL; keeps `/api/`, `/img/`, `http(s)` image links; ignores plain links and data URIs; first-seen order.
- `buildZipBlob` with a mock `fetchFn`:
  - two distinct images both 200 → both added, both links rewritten to `images/…`, `missing` empty.
  - same URL referenced twice → fetched once, one file in zip, both occurrences rewritten.
  - one 200 + one 404 → fetched one added & rewritten; the 404 URL kept verbatim and listed in `missing`.
  - zero images in md → zip contains only `<docName>.md`, `missing` empty.
  - assert zip contents via `JSZip.loadAsync(blob)` (file list + rewritten md text).
- `tsc --noEmit` clean; full suite green.

**Browser-verify (Chrome MCP, :5175):**
- Tutor answer with figures → per-answer export → unzip downloaded `.zip`, confirm `images/` holds the figure files and the `.md` links point at `images/…`.
- Topbar export of the conversation → confirm full transcript zip.
- Console clean.

## Docs to update on completion

- `docs/services/chat.md` — update the "Export to Markdown" subsection to "Export to Zip (Markdown + images)".
- `docs/system/changelog.md` — dated entry with verified result.
- `docs/common ground/Elements/index.html` — extend §17 (or add §18) noting the zip upgrade; pill → ✓ after verify.

## Out of scope (YAGNI)

- Spinner/progress UI for the fetch wait.
- Surfacing `missing[]` to the user (kept internal; links remain).
- Backend zip endpoint, PDF/HTML, re-import.
