# H003 — pre-registered statistical comparison

Source: `/Users/jamisonburks/lab_tracker/experiments/H003_substrate_lift/results/metrics.csv`  ·  α = 0.05

## PRIMARY — calibration & truthfulness (lower is better; want substrate < bare)

Family of 6 paired tests (2 contrasts × 3 metrics), corrected across the family (Bonferroni + BH-FDR).

| contrast | metric | n | bare | +substrate | Δ (sub−bare) | Cohen dz | p | p_bonf | p_BH | dir? | sig(bonf) | sig(BH) |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|
| qwen3:14b +substrate vs bare | ece | 3 | 0.089 | 0.097 | +0.008 | 0.398 | 0.562 | 1.000 | 0.843 | ✗ | · | · |
| qwen3:14b +substrate vs bare | confidently_wrong_rate | 3 | 0.333 | 0.187 | -0.146 | -5.338 | 0.011 | 0.069 | 0.034 | ✓ | · | ✓ |
| qwen3:14b +substrate vs bare | hallucination_rate | 3 | 0.000 | 0.000 | +0.000 | 0.000 | 1.000 | 1.000 | 1.000 | ✗ | · | · |  _(no variation)_
| frontier +substrate vs bare | ece | 3 | 0.303 | 0.200 | -0.104 | -3.787 | 0.022 | 0.135 | 0.045 | ✓ | · | ✓ |
| frontier +substrate vs bare | confidently_wrong_rate | 3 | 0.333 | 0.033 | -0.300 | -20.410 | 0.001 | 0.005 | 0.005 | ✓ | ✓ | ✓ |
| frontier +substrate vs bare | hallucination_rate | 3 | 0.000 | 0.000 | +0.000 | 0.000 | 1.000 | 1.000 | 1.000 | ✗ | · | · |  _(no variation)_

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

- Primary (calibration/truthfulness, both contrasts survive Bonferroni+BH): ✗
- Secondary (ranking not materially degraded): ✓
- Secondary (per-grade confidence monotone): ✓

### **NOT SUPPORTED / FALSIFIED**

_Note: with n=3 seeds the paired tests are low-power; a non-significant result is weak evidence, not proof of no effect. Report effect sizes (Cohen's dz) alongside p-values._

