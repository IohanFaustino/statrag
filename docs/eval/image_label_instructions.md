# Image-pertinence labelling guide

Goal: produce a small (~30 row) ground-truth CSV so the two-tier
image judge can be measured with real precision / recall numbers.

## 1. Generate the CSV

```
.venv/bin/python ops/scripts/build_image_label_set.py \
    --out data/eval/image_label_set.csv \
    --per-query 4
```

This walks 8 seed queries × top-4 image candidates per query → ~32 rows.
Adjust ``--queries`` to add your own.

## 2. Fill the two empty columns

Open `data/eval/image_label_set.csv` in a spreadsheet or text editor.
For every row:

- **`label_include`** = `1` if the image **should** appear in an answer
  to the query; `0` if it should not.
- **`label_aspect`** = which DeepTutorAnswer section the figure belongs
  to. Pick one of:

  | aspect              | when to use                                                      |
  |---------------------|------------------------------------------------------------------|
  | `tldr`              | summary diagram conveying the headline answer                    |
  | `definition`        | venn / schematic / formal block diagram                           |
  | `formal_statement`  | equation, derivation, or proof sketch                            |
  | `intuition`         | analogy / informal sketch                                        |
  | `examples`          | scatter plot, worked example, table of cases                      |
  | `trade_offs`        | comparison curve, bias-variance curve, ROC                       |
  | `further_reading`   | high-level roadmap diagram                                       |

  Leave blank when `label_include = 0`.

- **`notes`** is optional free-text (skip when obvious).

## 3. Tips

- If the caption is empty or noise, mark `label_include = 0`.
- Decorative photos / book covers / chapter front-matter: `0`.
- When unsure, pick the closest aspect; the metric tolerates one-aspect
  drift via a soft accuracy score.
- 5-10 minutes per row is too long; trust your gut.

## 4. Run quality eval

```
.venv/bin/pytest -m quality_images src/services/chat/tests/test_image_judge_quality.py -s
```

The default `pytest src/services/chat/tests/` lane deselects the
`quality_images` marker so the live API + label CSV are never required
for normal regression. Run with the marker filter above to opt in.

Reports:
- precision, recall, F1 of the judge's include verdict
- placement accuracy (exact + soft)
- median latency overhead per query
- vision-call count per query
- token cost per query

KPIs (initial targets):

| metric              | target  |
|---------------------|---------|
| precision           | ≥ 0.80  |
| recall              | ≥ 0.70  |
| F1                  | ≥ 0.74  |
| placement accuracy  | ≥ 0.65  |
| latency overhead    | < 2000ms median |
| token overhead      | < 500 / query   |
| vision calls        | ≤ 2 / query     |

When KPIs drop, tune `TUTOR_DEEP_TIER1_INCLUDE` /
`TUTOR_DEEP_TIER1_EXCLUDE` thresholds in `agents/deep_tutor.py` (and the
image judge env vars).
