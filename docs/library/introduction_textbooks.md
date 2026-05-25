# `introduction_textbooks`

Qdrant collection: `introduction_textbooks` (paired with `introduction_images`).
Field: `introduction`.

## Books

| Slug | Name | Authors | Year | Edition | Theme | Chapters | Chunks | Images |
|---|---|---|---|---|---|---|---|---|
| `islp` | An Introduction to Statistical Learning with Applications in Python | Gareth James, Daniela Witten, Trevor Hastie, Robert Tibshirani, Jonathan Taylor | 2023 | 1st | Machine Learning | 12 | 502 | 155 |
| `hansen` | Probability and Statistics for Economists | Bruce E. Hansen | 2022 | 1st | Probability and Statistics | 18 | 358 | 169 |
| `neal` | Introduction to Causal Inference from a Machine Learning Perspective | Brady Neal | 2020 | draft | Causal Inference | 13 | 90 | 118 |
| `peck` | Introduction to Statistics and Data Analysis | Roxy Peck, Chris Olsen, Jay L. Devore | 2010 | 4th | Introductory Statistics | 15 | 169 | 657 |
| `wooldridge` | Introductory Econometrics — A Modern Approach | Jeffrey M. Wooldridge | 2018 | 7th | Econometrics | 19 | 312 | 72 |
| `cunningham` | Causal Inference: The Mixtape | Scott Cunningham | 2021 | 1st | Causal Inference | 10 | 140 | 127 |
| `stock_watson` | Introduction to Econometrics | James H. Stock, Mark W. Watson | 2019 | 4th | Econometrics | 19 | 180 | 1 |
| `murphy` | Probabilistic Machine Learning: An Introduction | Kevin P. Murphy | 2022 | 1st | Probabilistic Machine Learning | 23 | 674 | 13 |

## Notes

- `cunningham`: source pre-processed (`src/ingestion/processed/cunningham_preproc.py`) — flat OCR + page-bleed dupes.
- `stock_watson`: EPUB-MD with HTML-laden headers. Preproc strips `<span>` tags (`stock_watson_preproc.py`).
- `murphy`: EPUB-MD with no markdown headers — chapter/section heads encoded as TOC-back links `[**N Title**](#toc...)`. Preproc rewrites them as `#`/`##`/`###` (`murphy_preproc.py`).
