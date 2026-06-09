---
name: gap-augment
description: Fill chapter gap queries from other corpus books and Wikipedia, returning footnotes only (including formulas), judging fit before citing.
---

# Gap Augment

## When to Use
When the augmentor subagent processes /plan/queries.md.

## Instructions
1. For each `POINT :: query`, call retrieve_corpus (other books) and/or
   wikipedia_lookup.
2. Judge fit; discard off-topic results.
3. Write a footnote to /footnotes/<point>.md — marker, augmenting text (formulas
   as `$...$` / `$$...$$`), and source (book §section or Wikipedia URL).
4. End the file with `# COVERAGE: <query> = done|unfilled` per query.
5. Never modify curated body text.
