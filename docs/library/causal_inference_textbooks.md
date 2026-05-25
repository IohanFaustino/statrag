# `causal_inference_textbooks`

Qdrant collection: `causal_inference_textbooks` (paired with `causal_inference_images`).
Field: `causal_inference`.

## Books

| Slug | Name | Authors | Year | Edition | Theme | Chapters | Chunks | Images |
|---|---|---|---|---|---|---|---|---|
| `hernan` | Causal Inference: What If | Miguel A. Hernán, James M. Robins | 2020 | 2020 edition | Causal Inference | 22 | 122 | 128 |
| `peters` | Elements of Causal Inference: Foundations and Learning Algorithms | Jonas Peters, Dominik Janzing, Bernhard Schölkopf | 2017 | 1st | Causal Inference | 10 | 110 | 83 |
| `pearl` | Causal Inference in Statistics: A Primer | Judea Pearl, Madelyn Glymour, Nicholas P. Jewell | 2016 | 1st | Causal Inference | 4 | 55 | 49 |
| `morgan` | Handbook of Causal Analysis for Social Research | Stephen L. Morgan (ed.) | 2013 | 1st | Causal Inference | 19 | 283 | 72 |

## Notes

- `morgan`: source pre-processed (`src/ingestion/processed/morgan_preproc.py`) — flat OCR with `# Chapter N` heads + flat section H1s. Yaml `source_path` points to `src/ingestion/processed/morgan_fixed.md`.
