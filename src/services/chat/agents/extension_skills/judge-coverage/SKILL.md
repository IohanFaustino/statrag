---
name: judge-coverage
description: Assemble the final ExtensionDigest JSON from curated points + footnotes and report unfilled gap queries.
---

# Judge Coverage

## When to Use
When the judge assembles the final result and decides completeness.

## Instructions
1. Read /curated/timeline.md and /footnotes/*.md.
2. Build ExtensionPoint objects in order; attach footnotes (kind corpus|wikipedia).
3. Ensure curated_text holds no augmentation.
4. Collect unfilled queries into unfilled_gaps.
5. Emit ONLY the ExtensionDigest JSON.
