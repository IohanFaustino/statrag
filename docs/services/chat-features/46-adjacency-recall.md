# 46 — Recall upgrades: adjacent-section expansion, TF weight, author cap

## Why

"What is the bias-variance tradeoff?" gave the bias formula but not the
variance one. Even after the query-planner + coverage check (doc 45), the
variance-formula chunk often lives in the **subsection right after** the bias
one — never pulled, because expansion was same-section only. Plus two smaller
levers: term-frequency weight and the author cap.

## 1 · Adjacent-section (sibling) expansion — rerank-gated

`density._fetch_neighbor_chunks(book_slug, section_id, page_from, …)`:
- Finds the nearest sections **before/after** the selected one via the
  `page_from` reading order (page-band scroll), **sibling-prefiltered** to the
  same parent (`_parent_section`: "2.2.1" → "2.2").
- Returns their lead chunks as low-score `_PseudoPoint`s.
`deep_tutor._density_select` appends these to the expanded pool; the **existing
cross-encoder rerank + `final_top_n` cut is the gate** — irrelevant neighbors
drop out. No tuned threshold. Env `TUTOR_NEIGHBOR_EXPAND` (1). Best-effort
(scroll errors → no neighbors). Because neighbors are candidates *before* the
coverage check, the "coverage tries neighbors first" intent is satisfied here.

## 2 · Term-frequency weight

`density._section_score(count_norm, rrf_norm, alpha)` already blends concept-TF
count vs RRF score. `alpha` is now `TUTOR_DENSITY_ALPHA` (0.6). Raising it makes
term frequency matter more in section ranking. (True BM25/sparse reweighting is
deferred — the hybrid query uses Qdrant native unweighted `Fusion.RRF`; weighting
would need a manual-fusion rewrite.)

## 3 · More than 3 authors

Author count is Auto (planner-suggested, capped). `_DIVERSITY_MAX` default
raised 4 → 5 (env `TUTOR_DIVERSITY_MAX_AUTHORS`); the `perspectives` prompt nudges
toward more for broad/comparative questions; the diversity dropdown adds 5/6.
Caveat: more authors = lower-ranked books + busier answer + (orchestrator mode)
+1 worker call each.

## Config

| Knob | Default | Meaning |
|---|---|---|
| `TUTOR_NEIGHBOR_EXPAND` | `1` | adjacent sibling-section expansion |
| `TUTOR_DENSITY_ALPHA` | `0.6` | concept-TF weight in section scoring |
| `TUTOR_DIVERSITY_MAX_AUTHORS` | `5` | author cap / Auto ceiling |

## Tests

`src/services/chat/tests/test_adjacency_recall.py` — `_parent_section`,
neighbor sibling/order/dedup/graceful, author cap ≥5.

## Verified

In-browser, "What is the bias-variance tradeoff?" → formal statement shows both
`Bias(θ̂)=E(θ̂)−θ` and `Variance(θ̂)=E(θ̂²)−(E(θ̂))²`; 8 sources; 0 errors.
