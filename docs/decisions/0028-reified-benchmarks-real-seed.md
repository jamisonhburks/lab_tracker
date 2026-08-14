# ADR-0028: Reified benchmark results + real arXiv seeding of the ML layer

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
ADR-0027 added the ML method layer but (a) represented benchmark claims as bare
`achieves` edges (no value/date to compare over time) and (b) seeded authorship
illustratively. Both are addressed here.

## Decision
- **Reify benchmark results** — `ml_schema.BenchmarkResult(model, dataset, metric, value,
  date, higher_is_better, source)` is a first-class reified node (the ML parallel to a
  reified biomedical Association+Evidence): value and date are stored, so
  `ml_schema.leaderboard(...)` ranks a `(dataset, metric)` and shows the temporal churn,
  and the result is traversable (`model —reports_result→ BenchmarkResult —on_dataset→
  Dataset —measures→ Metric`). Benchmark edges stay LOW-trust (`benchmark:` source).
- **Real seeding** — `ml_seed.py` fetches **real first/last author, year, title** from the
  **arXiv API** for a curated set of ~13 seminal methods, and caches a fused graph to
  `seeds/ml_fused.json` (tracked). Lineage, labs, benchmark numbers, and the biomedical
  bridge are hand-curated from public knowledge (arXiv has neither affiliations nor
  benchmark values). New backend **`KG_BACKEND=ml`** loads it.

## Rationale & evidence
- **Verified** (`KG_BACKEND=ml`, 82 nodes / 82 edges): real arXiv authorship —
  ResNet → **Kaiming He / Jian Sun** / Microsoft Research (2015); ViT → **Dosovitskiy /
  Houlsby** / Google (2020). Reified leaderboards: GLUE `RoBERTa 88.5 (2019) > BERT 80.5
  (2018)`, ImageNet `ViT 88.5 (2020) > ResNet 78.3 (2015)`. A benchmark result is a
  traversable node.
- **Honest provenance tiers**: authorship/dates are API-**real**; lineage + benchmark
  values are curated-**real** (public knowledge), and benchmark values are representative
  + low-trust by design. Full-corpus expansion would come from Papers-With-Code / AI-KG /
  CSO / DBLP — the mechanism is in place (`ml_seed.py`).

## Consequences
- Method effectiveness is now time-aware and comparable — you can watch a method get
  superseded, which is the whole point of treating methods as non-stationary artifacts.
- `seeds/ml_fused.json` is a tracked, reproducible real seed (re-buildable via
  `python ml_seed.py`); the `ml` backend loads it offline.
