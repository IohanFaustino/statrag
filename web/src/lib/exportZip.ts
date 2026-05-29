// Bundles a Markdown string + its referenced images into a zip Blob.
// extractImageUrls + imageFilename are pure; buildZipBlob (later task) does the
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
  // For API-style URLs (e.g. /api/figures?path=foo.jpg), the real filename is
  // in the `path` query parameter, not the path segment.
  let filenameSource: string;
  const qIdx = url.indexOf("?");
  if (qIdx !== -1) {
    const qs = url.slice(qIdx + 1);
    const pathParam = new URLSearchParams(qs).get("path") ?? "";
    filenameSource = pathParam || "";
  } else {
    filenameSource = "";
  }

  // Fall back to last path segment when no query-param filename found.
  if (!filenameSource) {
    const pathPart = url.split("?")[0];
    filenameSource = pathPart.split("/").filter(Boolean).pop() ?? "";
    // If the segment looks like a bare API path component (no extension and we
    // had a query string), treat it as no useful name.
    if (qIdx !== -1 && filenameSource.indexOf(".") === -1) {
      filenameSource = "";
    }
  }

  const dot = filenameSource.lastIndexOf(".");
  const rawBase = dot > 0 ? filenameSource.slice(0, dot) : filenameSource;
  const urlExt = dot > 0 ? filenameSource.slice(dot + 1).toLowerCase() : "";
  const base = (rawBase || "figure").replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "figure";
  const ext = urlExt || (contentType && CT_EXT[contentType.split(";")[0].trim()]) || "img";
  return `${base}-${shortHash(url)}.${ext}`;
}
