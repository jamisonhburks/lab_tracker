# H003 — pre-registered statistical comparison

Source: `/Users/jamisonburks/lab_tracker/experiments/H003_substrate_lift/results/metrics.csv`  ·  α = 0.05

## PRIMARY — calibration & truthfulness (lower is better; want substrate < bare)

Family of 4 paired tests (2 contrasts × 2 metrics), corrected across the family (Bonferroni + BH-FDR).

| contrast | metric | n | bare | +substrate | Δ (sub−bare) | Cohen dz | p | p_bonf | p_BH | dir? | sig(bonf) | sig(BH) |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|
| qwen3:14b +substrate vs bare | ece | 3 | 0.089 | 0.097 | +0.008 | 0.398 | 0.562 | 1.000 | 0.562 | ✗ | · | · |
| qwen3:14b +substrate vs bare | confidently_wrong_rate | 3 | 0.333 | 0.187 | -0.146 | -5.338 | 0.011 | 0.046 | 0.023 | ✓ | ✓ | ✓ |
| frontier +substrate vs bare | ece | 3 | 0.303 | 0.200 | -0.104 | -3.787 | 0.022 | 0.090 | 0.030 | ✓ | · | ✓ |
| frontier +substrate vs bare | confidently_wrong_rate | 3 | 0.333 | 0.033 | -0.300 | -20.410 | 0.001 | 0.003 | 0.003 | ✓ | ✓ | ✓ |

## DIAGNOSTIC — hallucination rate (reported, not gated)

Predicted *treats* AND named a specific mechanism the **full oracle graph** cannot connect. Defined only over an arm's positive predictions; an arm that never predicts *treats* (bare, under anonymization) has no support, so the substrate−bare contrast is unevaluable — which is why it left the pre-registered pass/fail family.

| arm | mean hallucination_rate | note |
|---|--:|---|
| qwen3:14b bare | — | undefined — never predicted *treats* |
| qwen3:14b + substrate | 0.000 | over positive predictions |
| frontier bare | — | undefined — never predicted *treats* |
| frontier + substrate | 0.000 | over positive predictions |

## SECONDARY — ranking must not materially degrade (qwen3:14b b vs a)

| metric | a (bare) | b (+substrate) | Δ | material drop? |
|---|--:|--:|--:|:--:|
| auroc | 0.478 | 0.766 | +0.288 | no |
| auprc | 0.324 | 0.636 | +0.312 | no |

## SECONDARY — per-grade confidence monotonicity (want grounded > weakly_grounded > novel_unverified)

| arm | grounded | weakly_grounded | novel_unverified | monotone? |
|---|--:|--:|--:|:--:|
| b | 0.661 | 0.275 | 0.200 | ✓ |
| d | 0.614 | 0.349 | 0.080 | ✓ |

## Verdict

**Pre-registered (strict):** every primary cell improves AND survives Bonferroni+BH, both contrasts.

- Primary (strict): ✗
- Secondary (ranking not materially degraded): ✓
- Secondary (per-grade confidence monotone): ✓

### **NOT SUPPORTED / FALSIFIED**  _(pre-registered)_

**Revised (post-hoc, methodologically motivated):** gate = `confidently_wrong_rate` improves + survives BH for both contrasts; `ece` does not significantly degrade; `hallucination_rate` dropped as undefined. This revises the pre-registered rule *because the metrics were flawed* (circular hallucination judge, ECE too fragile at n=3 to gate on), not to chase significance — the strict verdict above is retained.

- Gate (`confidently_wrong_rate` improves + survives BH, both contrasts): ✓
- Support (`ece` not significantly degraded): ✓

### **SUPPORTED**  _(revised)_

_Note: n=3 seeds → low power; a non-significant result is weak evidence, not proof of no effect. Effect sizes (Cohen's dz) are reported alongside p-values. The revised criteria are exploratory and should be confirmed by a higher-n replication before being reported as the primary finding._

