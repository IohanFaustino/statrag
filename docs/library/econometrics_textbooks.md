# `econometrics_textbooks`

Qdrant collection: `econometrics_textbooks` (paired with `econometrics_images`).
Field: `econometrics`.

## Books

| Slug | Name | Authors | Year | Edition | Theme | Chapters | Chunks | Images |
|---|---|---|---|---|---|---|---|---|
| `baltagi` | Econometrics | Badi H. Baltagi | 2021 | 6th | Econometrics | 14 | 148 | 45 |
| `gujarati` | Basic Econometrics | Damodar N. Gujarati, Dawn C. Porter | 2008 | 5th | Econometrics | 22 | 260 | 249 |
| `atwan` | Time Series Analysis with Python Cookbook | Tarek A. Atwan | 2026 | 1st | Time Series | 14 | 844 | 427 |
| `das` | Econometrics in Theory and Practice: Analysis of Cross Section, Time Series and Panel Data with Stata 15.1 | Panchanan Das | 2019 | 1st | Applied Econometrics with Stata | 18 | 394 | 3278 |
| `pesaran` | Time Series and Panel Data Econometrics | M. Hashem Pesaran | 2015 | 1st | Time Series and Panel Data | 33 | 666 | 65 |
| `spark_ts` | Time Series Analysis with Spark: A practical guide to processing, modeling, and forecasting time series with Apache Spark | Yoni Ramaswami | 2024 | 1st | Time Series | n/a | n/a | 145 |

## Notes

- `atwan`: source pre-processed (`src/ingestion/processed/atwan_preproc.py`) — all `#` demoted to `##`, line numbers preserved. Cookbook format → many short sections per chapter.
- `pesaran`: source pre-processed (`src/ingestion/processed/pesaran_preproc.py`) — EPUB-converted markdown wraps every section header as a markdown link (`# [N.N Title](url)`). Preproc strips the link wrapper and inline image markdown from titles. Line numbers preserved one-for-one. Appendices excluded (ch33 stops at line 25129, before the Appendix sections).
