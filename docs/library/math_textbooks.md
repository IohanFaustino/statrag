# `math_textbooks`

Qdrant collection: `math_textbooks` (paired with `math_images`).
Field: `math`.

## Books

| Slug | Name | Authors | Year | Edition | Theme | Chapters | Chunks | Images |
|---|---|---|---|---|---|---|---|---|
| `lis_rosser` | Basic Mathematics for Economists | Mike Rosser, Piotr Lis | 2025 | 4th | Mathematics for Economics | 16 | 138 | 82 |
| `moss` | Mathematical Statistics for Applied Econometrics | Charles B. Moss | 2015 | 1st | Mathematical Statistics | 12 | 138 | 65 |
| `mackay` | Mathematical Foundations of Machine Learning | David MacKay | 2024 | 1st | Machine Learning Mathematics | 5 | 43 | 26 |

## Notes

- `mackay`: source pre-processed (`src/ingestion/processed/mackay_preproc.py`) — all `#` demoted to `##`. Cookbook/flat OCR pattern.
