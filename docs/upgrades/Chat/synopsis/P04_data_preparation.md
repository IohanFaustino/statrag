# P4 — Data Preparation (Polzer)

Cleaning, **chunking strategies**, **metadata enrichment**.

**Relevance**: medium (already chunked) / high (metadata).
- Metadata enrichment → enables payload filters (book/chapter/section/theme).
- Re-chunking unnecessary unless retrieval eval shows gaps.

**Take**: audit current Qdrant payloads, ensure book_slug/chapter/section/theme present. Add page_num if missing for navigator service.
