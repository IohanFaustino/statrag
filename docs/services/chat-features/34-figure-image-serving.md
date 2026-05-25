# 34 — Image preview in sources (figure serving)

## Purpose

Figure sources used to fall back to placeholder SVGs because raw absolute filesystem paths from Qdrant payloads can't be loaded by the browser. Now the backend serves figure images through a guarded endpoint and the frontend renders real previews.

## Where it lives

### Backend

- `src/services/chat/api.py::serve_figure` — new route `GET /api/figures?path=<url-encoded-abs-path>`.
  - Whitelists a set of root directories (figures must live inside one of them).
  - Extension guard: `.png`, `.jpg`, `.jpeg`, `.webp`, `.svg` only.
  - Returns 404 if path escapes the whitelist or the file is missing.
- `src/services/chat/retrieval.py::_chart_url` — builds `/api/figures?path=…` from the `image_path` field in the Qdrant figure payload. URL-encodes the path.

### Frontend

- `web/src/components/MessageThread.tsx` — `FigureCard` and `InlineFigure` accept a `chart` field:
  - If `chart.startsWith("/")` or `chart.startsWith("http")` → render `<img src={chart}>`.
  - Otherwise → fall back to the inline SVG placeholder (legacy path for figures without a resolvable image).

## Security

- Whitelist roots are configured at module load and never derived from request input.
- `Path.resolve()` + `is_relative_to()` check rejects traversal (`../`) before opening the file.
- Returned with `Cache-Control: public, max-age=3600` for static content; MIME inferred from extension.

## User-facing behavior

- Sources panel + inline figure blocks now show actual matplotlib/Manim/textbook figure renders.
- Figures without an `image_path` payload (older ingests) still render the SVG placeholder.
- 404 cases (deleted asset, path outside whitelist) silently fall back to the placeholder without breaking layout.
