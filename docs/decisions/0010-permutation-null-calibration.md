# ADR-0010: Permutation-null calibration of the realism metric

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
The realism metric (degree-weighted path count) is comparative but **inflated by
graph density** — in a dense KG almost any two nodes connect via hubs, so even
distant pairs score "plausible." The raw number isn't a calibrated probability.

## Options considered
- Leave it heuristic (documented as such).
- **Degree-preserving permutation null** (the Rephetio calibration).
- Time-sliced evaluation (needs edge timestamps Hetionet lacks — deferred).

## Decision
`calibrate_link` compares a pair's DWPC strength against **random pairs of the same
degree** and reports a **percentile / empirical p-value**.

## Rationale & evidence
- Directly addresses the hub-bias caveat from the lit review (ADR-0005; PNAS 2025:
  a bias-only model can beat sophisticated GNNs under naïve benchmarking).
- **Measured:** Crohn's ↔ UC strength 4.07 vs null 0.96 → **100th %ile, p=0.000
  (distinctive)**; epilepsy ↔ breast cancer 1.76 vs 0.88 → **84th %ile, p=0.16
  (above chance, not significant)**. Calibration separates real signal from
  density artifact — a high raw score typical of random pairs is exposed.

## Consequences
- Turns a heuristic into an honest, comparative statistic. Full probability
  calibration (against experimentally-validated outcomes) remains future work.
