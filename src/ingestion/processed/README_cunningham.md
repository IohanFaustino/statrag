# `cunningham_fixed.md` — preprocessing notes

Source: `/home/iohan/Documents/Converters/Cloud based/Converters/Files/Output/Introduction/2021_Cunningham/vlm/2021_Cunningham.md`

**Why preprocessed**: Cunningham's OCR uses a single `#` for every header and repeats chapter/section titles across page breaks (page-header bleed). Default `regex_pass.py` would emit zero sections.

**Transforms applied** (one-off, not part of pipeline):

1. **Dedupe consecutive duplicate H1s** — same title twice in a row (normalized: lowercase + alnum only) → keep one. 37 lines removed.
2. **Promote non-chapter H1s to H2** — only the 10 known book-chapter titles stay as `#`; everything else `# X` becomes `## X`. 188 promotions.
3. **First-occurrence chapter rule** — a chapter title is recognized as H1 only on its FIRST content appearance. Later occurrences (e.g. a per-chapter "Conclusion" section reusing the title) get demoted to H2.

Chapter list (normalized match):
`Introduction`, `Probability and Regression Review`, `Directed Acyclic Graphs`, `Potential Outcomes Causal Model`, `Matching and Subclassification`, `Regression Discontinuity`, `Instrumental Variables`, `Panel Data`, `Difference-in-Differences`, `Synthetic Control`.

**Reproduce**: run the inline Python in the chat session of 2026-05-16 (changelog entry #46) or copy from `library/_processed/cunningham_preproc.py` if added later.

**If re-ingesting**: regenerate this file from source before running pipeline. Yaml `source_path` points here.
