# Chat Zip Export (Markdown + Images) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The existing chat download buttons now export a `.zip` containing the Markdown plus every referenced image (deduped, fetched, links rewritten to relative paths).

**Architecture:** Frontend-only, builds on the shipped `.md` serializer. A new pure-ish module `web/src/lib/exportZip.ts` extracts image URLs from a Markdown string, fetches each (deduped, same-origin), bundles them under `images/` in a JSZip with the rewritten `.md`, and returns a Blob. App handlers become async and always emit `.zip`. The DOM download helper is generalized from `downloadMarkdown(filename, content)` to `downloadBlob(filename, blob)`.

**Tech Stack:** TypeScript, React 18, Vite, vitest, **jszip** (new dep). Types from `web/src/types.ts`.

---

## File Structure

- **Modify** `web/package.json` — add `jszip` dependency.
- **Create** `web/src/lib/exportZip.ts` — `extractImageUrls`, `buildZipBlob`, plus private `imageFilename` helper. One responsibility: Markdown-string + images → zip Blob.
- **Create** `web/src/lib/exportZip.test.ts` — vitest, mock `fetchFn`, assert via `JSZip.loadAsync`.
- **Modify** `web/src/lib/exportMarkdown.ts` — replace `downloadMarkdown` with `downloadBlob`.
- **Modify** `web/src/App.tsx` — async handlers, always `.zip`, import `downloadBlob` + `buildZipBlob`.

Test commands (run from repo root; note `cd web`):
- `cd web && npx vitest run src/lib/exportZip.test.ts`
- `cd web && npx tsc --noEmit`
- `cd web && npx vitest run` (full suite)
- Dev stack already on :5175 via `./scripts/dev.sh`.

---

## Task 1: Add jszip + `extractImageUrls` and filename helper

**Files:**
- Modify: `web/package.json`
- Create: `web/src/lib/exportZip.ts`
- Test: `web/src/lib/exportZip.test.ts`

- [ ] **Step 1: Install jszip**

Run: `cd web && npm install jszip`
Expected: `jszip` added to `dependencies` in `web/package.json`; `package-lock.json` updated. (JSZip 3.x ships its own TypeScript types — no `@types/jszip` needed.)

- [ ] **Step 2: Write the failing tests for `extractImageUrls` + `imageFilename`**

Create `web/src/lib/exportZip.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { extractImageUrls, imageFilename } from "./exportZip";

describe("extractImageUrls", () => {
  it("extracts /api, /img and http(s) image links", () => {
    const md = [
      "![a](/api/figures?path=x.jpg)",
      "![b](/img/fig.png)",
      "![c](https://example.com/p.png)",
    ].join("\n\n");
    expect(extractImageUrls(md)).toEqual([
      "/api/figures?path=x.jpg",
      "/img/fig.png",
      "https://example.com/p.png",
    ]);
  });

  it("dedupes a repeated url, first-seen order", () => {
    const md = "![a](/img/x.png)\n\n![again](/img/x.png)\n\n![b](/img/y.png)";
    expect(extractImageUrls(md)).toEqual(["/img/x.png", "/img/y.png"]);
  });

  it("ignores plain links and data URIs", () => {
    const md = "[text](/api/foo) and ![d](data:image/png;base64,AAAA)";
    expect(extractImageUrls(md)).toEqual([]);
  });
});

describe("imageFilename", () => {
  it("uses the url basename + a stable short hash + extension", () => {
    const a = imageFilename("/img/scatter.png");
    expect(a).toMatch(/^scatter-[a-z0-9]+\.png$/);
    // Stable: same url → same name.
    expect(imageFilename("/img/scatter.png")).toBe(a);
  });

  it("derives extension from content type when url has none", () => {
    expect(imageFilename("/api/figures?path=x", "image/jpeg")).toMatch(/\.jpg$/);
  });

  it("falls back to figure + img extension", () => {
    expect(imageFilename("/api/figures?path=")).toMatch(/^figure-[a-z0-9]+\.img$/);
  });

  it("different urls with same basename get different names", () => {
    const a = imageFilename("/a/fig.png");
    const b = imageFilename("/b/fig.png");
    expect(a).not.toBe(b);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd web && npx vitest run src/lib/exportZip.test.ts`
Expected: FAIL — `Failed to resolve import "./exportZip"`.

- [ ] **Step 4: Create `web/src/lib/exportZip.ts` with the two helpers (buildZipBlob added in Task 2)**

```ts
// Bundles a Markdown string + its referenced images into a zip Blob.
// extractImageUrls + imageFilename are pure; buildZipBlob (Task 2) does the
// fetching/zipping. Same-origin images only in practice (/api, /img).

// Markdown image syntax: ![alt](url). Capture the url.
const IMAGE_MD_RE = /!\[[^\]]*\]\(([^)\s]+)\)/g;

function isBundleable(url: string): boolean {
  return (
    url.startsWith("/api/") ||
    url.startsWith("/img/") ||
    url.startsWith("http://") ||
    url.startsWith("https://")
  );
}

export function extractImageUrls(md: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const m of md.matchAll(IMAGE_MD_RE)) {
    const url = m[1];
    if (isBundleable(url) && !seen.has(url)) {
      seen.add(url);
      out.push(url);
    }
  }
  return out;
}

// Small stable string hash (djb2) → base36, for collision-free filenames.
function shortHash(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h.toString(36);
}

const CT_EXT: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/jpg": "jpg",
  "image/png": "png",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/svg+xml": "svg",
};

// Deterministic, collision-resistant filename for an image URL.
export function imageFilename(url: string, contentType?: string): string {
  // Last path segment, before any query string.
  const path = url.split("?")[0];
  const segment = path.split("/").filter(Boolean).pop() ?? "";
  const dot = segment.lastIndexOf(".");
  const rawBase = dot > 0 ? segment.slice(0, dot) : segment;
  const urlExt = dot > 0 ? segment.slice(dot + 1).toLowerCase() : "";
  const base = (rawBase || "figure").replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "figure";
  const ext = urlExt || (contentType && CT_EXT[contentType.split(";")[0].trim()]) || "img";
  return `${base}-${shortHash(url)}.${ext}`;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd web && npx vitest run src/lib/exportZip.test.ts`
Expected: PASS (both describe blocks).

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/package-lock.json web/src/lib/exportZip.ts web/src/lib/exportZip.test.ts
git commit -m "feat(web): jszip dep + image-url extraction for zip export

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `buildZipBlob` — fetch images, rewrite links, zip

**Files:**
- Modify: `web/src/lib/exportZip.ts`
- Test: `web/src/lib/exportZip.test.ts`

- [ ] **Step 1: Add the failing tests**

Append to `web/src/lib/exportZip.test.ts`:

```ts
import JSZip from "jszip";
import { buildZipBlob } from "./exportZip";

// Build a fake fetch that returns a tiny image for listed urls, 404 otherwise.
function fakeFetch(ok: Record<string, string>): typeof fetch {
  return (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url in ok) {
      return {
        ok: true,
        headers: { get: (h: string) => (h.toLowerCase() === "content-type" ? ok[url] : null) },
        blob: async () => new Blob(["IMGBYTES"], { type: ok[url] }),
      } as unknown as Response;
    }
    return { ok: false, status: 404, headers: { get: () => null }, blob: async () => new Blob([]) } as unknown as Response;
  }) as typeof fetch;
}

describe("buildZipBlob", () => {
  it("bundles fetched images and rewrites their links to images/…", async () => {
    const md = "![a](/img/x.png)\n\n![b](/api/figures?path=y.jpg)";
    const fetchFn = fakeFetch({ "/img/x.png": "image/png", "/api/figures?path=y.jpg": "image/jpeg" });
    const { blob, missing } = await buildZipBlob(md, { docName: "doc" }, fetchFn);
    expect(missing).toEqual([]);
    const zip = await JSZip.loadAsync(blob);
    const names = Object.keys(zip.files).sort();
    expect(names).toContain("doc.md");
    const imgs = names.filter((n) => n.startsWith("images/"));
    expect(imgs).toHaveLength(2);
    const text = await zip.file("doc.md")!.async("string");
    expect(text).toContain("](images/");
    expect(text).not.toContain("](/img/x.png)");
    expect(text).not.toContain("](/api/figures?path=y.jpg)");
  });

  it("fetches a repeated url once and rewrites both occurrences", async () => {
    const md = "![a](/img/x.png)\n\n![again](/img/x.png)";
    const { blob } = await buildZipBlob(md, { docName: "doc" }, fakeFetch({ "/img/x.png": "image/png" }));
    const zip = await JSZip.loadAsync(blob);
    expect(Object.keys(zip.files).filter((n) => n.startsWith("images/"))).toHaveLength(1);
    const text = await zip.file("doc.md")!.async("string");
    expect(text.match(/\]\(images\//g)).toHaveLength(2);
    expect(text).not.toContain("/img/x.png");
  });

  it("keeps the link and lists missing for a failed fetch", async () => {
    const md = "![ok](/img/x.png)\n\n![bad](/img/missing.png)";
    const { blob, missing } = await buildZipBlob(md, { docName: "doc" }, fakeFetch({ "/img/x.png": "image/png" }));
    expect(missing).toEqual(["/img/missing.png"]);
    const zip = await JSZip.loadAsync(blob);
    expect(Object.keys(zip.files).filter((n) => n.startsWith("images/"))).toHaveLength(1);
    const text = await zip.file("doc.md")!.async("string");
    expect(text).toContain("](/img/missing.png)"); // untouched
    expect(text).toContain("](images/");           // the ok one rewritten
  });

  it("zips just the md when there are no images", async () => {
    const { blob, missing } = await buildZipBlob("no images here", { docName: "doc" }, fakeFetch({}));
    expect(missing).toEqual([]);
    const zip = await JSZip.loadAsync(blob);
    expect(Object.keys(zip.files)).toEqual(["doc.md"]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/lib/exportZip.test.ts`
Expected: FAIL — `buildZipBlob` is not exported.

- [ ] **Step 3: Implement `buildZipBlob`**

Append to `web/src/lib/exportZip.ts`:

```ts
import JSZip from "jszip";

export interface ZipResult {
  blob: Blob;
  missing: string[];
}

// Escape a string for use as a literal in a RegExp.
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export async function buildZipBlob(
  markdown: string,
  opts: { docName: string },
  fetchFn: typeof fetch = fetch,
): Promise<ZipResult> {
  const urls = extractImageUrls(markdown);
  const zip = new JSZip();
  const missing: string[] = [];
  let md = markdown;

  for (const url of urls) {
    try {
      const res = await fetchFn(url);
      if (!res.ok) {
        missing.push(url);
        continue;
      }
      const data = await res.blob();
      const ct = res.headers.get("content-type") ?? undefined;
      const name = imageFilename(url, ct);
      zip.file(`images/${name}`, data);
      // Rewrite every occurrence of this exact url to the relative path.
      md = md.replace(new RegExp(escapeRegExp(url), "g"), `images/${name}`);
    } catch {
      missing.push(url);
    }
  }

  zip.file(`${opts.docName}.md`, md);
  const blob = await zip.generateAsync({ type: "blob" });
  return { blob, missing };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/lib/exportZip.test.ts`
Expected: PASS (all describe blocks).

- [ ] **Step 5: Typecheck + commit**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

```bash
git add web/src/lib/exportZip.ts web/src/lib/exportZip.test.ts
git commit -m "feat(web): buildZipBlob — fetch, dedupe, rewrite links, zip

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Generalize `downloadMarkdown` → `downloadBlob`

**Files:**
- Modify: `web/src/lib/exportMarkdown.ts`

- [ ] **Step 1: Replace the function**

In `web/src/lib/exportMarkdown.ts`, replace the entire `downloadMarkdown` function (currently lines 82–98):

```ts
export function downloadMarkdown(filename: string, content: string): void {
  try {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    // Best-effort, mirrors persist.ts: never throw from a UI handler.
    // eslint-disable-next-line no-console
    console.warn("[exportMarkdown] download failed", err);
  }
}
```

with:

```ts
export function downloadBlob(filename: string, blob: Blob): void {
  try {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    // Best-effort, mirrors persist.ts: never throw from a UI handler.
    // eslint-disable-next-line no-console
    console.warn("[exportMarkdown] download failed", err);
  }
}
```

Also update the file's top comment on line 2 from:
```ts
// function is downloadMarkdown (covered by browser-verify, not unit tests).
```
to:
```ts
// function is downloadBlob (covered by browser-verify, not unit tests).
```

- [ ] **Step 2: Typecheck (expect a known error in App, fixed in Task 4)**

Run: `cd web && npx tsc --noEmit`
Expected: errors ONLY in `web/src/App.tsx` (it still imports/calls `downloadMarkdown`). `exportMarkdown.ts` itself compiles. Do not fix App here — Task 4 does. If errors appear in any file other than `App.tsx`, stop and investigate.

- [ ] **Step 3: Run the existing markdown tests (unaffected)**

Run: `cd web && npx vitest run src/lib/exportMarkdown.test.ts`
Expected: PASS (those tests never referenced `downloadMarkdown`).

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/exportMarkdown.ts
git commit -m "refactor(web): downloadMarkdown -> generic downloadBlob

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Wire async zip handlers in App.tsx

**Files:**
- Modify: `web/src/App.tsx`

- [ ] **Step 1: Update the import**

In `web/src/App.tsx`, replace line 20:

```tsx
import { conversationToMarkdown, assistantMessageToMarkdown, slugify, downloadMarkdown } from "./lib/exportMarkdown";
```

with two import lines:

```tsx
import { conversationToMarkdown, assistantMessageToMarkdown, slugify, downloadBlob } from "./lib/exportMarkdown";
import { buildZipBlob } from "./lib/exportZip";
```

- [ ] **Step 2: Replace both handlers**

Replace the current `handleExportConversation` and `handleExportMessage` (lines 596–612):

```tsx
  const handleExportConversation = useCallback(() => {
    if (messages.length === 0) return;
    const title = activeConvTitle.replace(/\s+/g, " ").trim();
    const md = conversationToMarkdown(messages, { title });
    downloadMarkdown(`statrag-${slugify(title)}.md`, md);
  }, [messages, activeConvTitle]);

  const handleExportMessage = useCallback((idx: number) => {
    const msg = messages[idx];
    if (!msg || msg.role !== "assistant") return;
    const title = activeConvTitle.replace(/\s+/g, " ").trim();
    // 1-based ordinal of this answer among assistant messages.
    let n = 0;
    for (let i = 0; i <= idx; i++) if (messages[i].role === "assistant") n++;
    const nn = String(n).padStart(2, "0");
    downloadMarkdown(`statrag-${slugify(title)}-a${nn}.md`, assistantMessageToMarkdown(msg));
  }, [messages, activeConvTitle]);
```

with:

```tsx
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
    // 1-based ordinal of this answer among assistant messages.
    let n = 0;
    for (let i = 0; i <= idx; i++) if (messages[i].role === "assistant") n++;
    const nn = String(n).padStart(2, "0");
    const md = assistantMessageToMarkdown(msg);
    const { blob } = await buildZipBlob(md, { docName: `${slug}-a${nn}` });
    downloadBlob(`statrag-${slug}-a${nn}.zip`, blob);
  }, [messages, activeConvTitle]);
```

> Note: `onExportConversation` / `onExportMessage` props are typed as `() => void` / `(idx) => void`. Passing an `async` function (which returns a `Promise<void>`) is assignable to a `() => void` prop in TS, so no prop-type change is needed. The buttons already exist (shipped) and need no markup change.

- [ ] **Step 3: Typecheck + full test suite**

Run: `cd web && npx tsc --noEmit && npx vitest run`
Expected: typecheck clean; all suites green (existing 71 + new exportZip tests).

- [ ] **Step 4: Commit**

```bash
git add web/src/App.tsx
git commit -m "feat(web): chat export buttons now download .zip (md + images)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Browser-verify on :5175 (Chrome MCP) + docs

**Files:**
- Modify: `docs/services/chat.md`
- Modify: `docs/system/changelog.md`
- Modify: `docs/common ground/Elements/index.html`

- [ ] **Step 1: Confirm dev stack is up**

Run: `curl -s http://localhost:8766/api/health && curl -s -o /dev/null -w " %{http_code}\n" http://localhost:5175/`
Expected: `{"status":"ok"}` and `200`. If not, run `./scripts/dev.sh` in the background.

- [ ] **Step 2: Browser-verify per-answer zip (Chrome MCP, :5175)**

Open `http://localhost:5175/`. Send a tutor question whose answer includes figures (e.g. "Define variance in one sentence." — verified earlier to embed figure images). Wait for completion. Click the per-answer export icon. Confirm a `statrag-*-a01.zip` download.

- [ ] **Step 3: Inspect the downloaded zip**

Run (adjust filename to the actual downloaded file):
```bash
cd /tmp && rm -rf ziptest && mkdir ziptest && unzip -o ~/Downloads/statrag-*-a01.zip -d ziptest && find ziptest -type f
```
Expected: a `*.md` at the root and an `images/` directory containing the figure files. Then:
```bash
grep -o "](images/[^)]*)" /tmp/ziptest/*.md | head
```
Expected: image links point at `images/…`, not `/api/figures…`.

- [ ] **Step 4: Browser-verify full-conversation zip**

Click the Topbar download button. Confirm a `statrag-<slug>.zip` download; unzip and confirm the `.md` (header + turns) plus the shared `images/` folder.

- [ ] **Step 5: Monitor console**

Use Chrome MCP `read_console_messages` (pattern `exportMarkdown|export|error|Error`) during the run. Expected: no errors.

- [ ] **Step 6: Update docs**

- `docs/services/chat.md`: change the "Export to Markdown" subsection to describe zip export — buttons download a `.zip` (Markdown + deduped images, links rewritten to `images/…`); both granularities; pure frontend via `web/src/lib/exportZip.ts` + `exportMarkdown.ts`; `jszip` dep; missing images keep their link.
- `docs/system/changelog.md`: prepend a dated (2026-05-29) entry summarizing the zip upgrade + the verified browser result.
- `docs/common ground/Elements/index.html`: extend §17 with a row/note for the zip upgrade (or add §18); keep the pill ✓ with the date.

- [ ] **Step 7: Commit**

```bash
git add docs/services/chat.md docs/system/changelog.md "docs/common ground/Elements/index.html"
git commit -m "docs: chat zip export (markdown + images)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Definition of Done

- [ ] `jszip` in `web/package.json`; `exportZip.ts` implemented (`extractImageUrls`, `imageFilename`, `buildZipBlob`).
- [ ] `downloadMarkdown` replaced by `downloadBlob`; no remaining references to `downloadMarkdown`.
- [ ] Both buttons emit `.zip` (md + deduped images; links rewritten; missing images keep link).
- [ ] `tsc --noEmit` clean; `vitest run` fully green (existing + new).
- [ ] Browser-verified on :5175: per-answer and full-conversation zips both unzip to `<doc>.md` + `images/…` with rewritten links; console clean.
- [ ] `docs/services/chat.md`, `changelog.md`, reference graph `index.html` updated.
- [ ] Chinese wall intact (no `src/` change).
