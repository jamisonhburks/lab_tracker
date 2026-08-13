# H001 Evaluation — T2D–AD Shared-Gene Differential Expression (SYNTHETIC)

**Experiment:** H001
**Hypothesis file:** `hypotheses/H001_t2d_ad_shared_genes.yaml`
**Metrics:** `experiments/H001/results/metrics.csv`
**Log:** `experiments/H001/logs/run.log`
**Runs completed:** 3 independent seeds (42, 123, 7) — meets `min_runs: 3`.
**Data:** SYNTHETIC with planted ground truth. Not real patient/GEO data.

## 1. Verdict on the success metric

**Success criterion:** ≥3 planted shared genes significant at BH-FDR < 0.05 with
|Cohen's d| ≥ 0.5, reproducibly across ≥3 seeds.

**Result: MET — and substantially exceeded.** All **7** planted-effect genes (IDE,
IAPP, INS, APOE, AKT1, LEP, PPARGC1A) passed BOTH thresholds (BH-FDR < 0.05 AND
|d| ≥ 0.5) in **all 3 seeds**. Zero genes passed in only some seeds.

**Verdict: REJECT H₀ / SUPPORT H₁** on the synthetic benchmark — recovering 7/7 of the
differentially expressed subset.

**CRITICAL CAVEAT:** This verdict is about the *analysis pipeline recovering known
planted truth*, not about T2D/AD biology. See Section 5.

## 2. Per-gene results (planted genes, mean across seeds)

| Gene | Central? | Planted shift | Mean Cohen's d | Mean BH p | Passed all 3 seeds |
|------|----------|--------------|----------------|-----------|--------------------|
| IDE | Yes | 1.0 | 1.353 | ~1e-16 | Yes |
| APOE | Yes | 1.1 | 1.317 | ~1e-14 | Yes |
| INS | Yes | 0.85 | 1.023 | ~1e-11 | Yes |
| IAPP | Yes | 0.9 | 0.980 | ~2e-9 | Yes |
| AKT1 | Yes | 0.8 | 0.919 | ~2e-6 | Yes |
| LEP | No (adipokine) | 0.6 | 0.863 | ~1.6e-5 | Yes |
| PPARGC1A | No (mito) | 0.55 | 0.684 | ~7.8e-5 | Yes |

The 5 mechanistically-central genes (IDE, IAPP, INS, APOE, AKT1) show the largest
effect sizes (d ≈ 0.9–1.35), tracking their larger planted shifts — a good estimator
sanity check. The 13 non-planted panel genes were never significant.

**Bonferroni vs BH contrast:** Over n=50 tests, both agree on the 7 planted genes in
seeds 42/123. BH is more permissive (graded threshold vs a flat ×50). In seed 7,
`NULL_GENE_008` had p_raw = 0.00396 → p_bonferroni = 0.198 (correctly NOT significant,
FWER controlled) but p_bh = 0.0248 (called significant) — textbook: Bonferroni protects
against any false positive at a power cost; BH permits a controlled fraction.

## 3. Multiple-testing / FDR behavior

- **False positives (non-planted called BH-significant):** 1 total across all seeds —
  `NULL_GENE_008` in seed 7. Seeds 42 and 123 had zero.
- **Consistent with FDR control?** Yes. Seed 7: 8 rejections, 1 false → FDP = 12.5%; a
  single realization above 5% is fully consistent with BH controlling the *expected*
  FDP. Pooled across seeds: 1 false / 22 rejections ≈ 4.5%, at the nominal level.
- **Correctness:** True effects recovered at high power (7/7 every seed); nulls
  suppressed (1 escape in 90 null-gene tests ≈ 1.1%); Bonferroni rejected the lone
  false positive while BH admitted it as expected. Desired error-control signature.

## 4. Reproducibility / stability

- **Significant-gene set:** exactly the 7 planted genes in seeds 42 and 123; those 7
  plus one null in seed 7. True-positive set is 100% stable; only variation is one
  expected false positive.
- **Effect-size stability:** per-gene Cohen's d tight across seeds (IDE 1.37/1.36/1.33;
  APOE 1.20/1.26/1.49).
- **Repro metadata (run.log):** Python 3.13.9 (Anaconda); numpy 2.3.5; pandas 2.3.3;
  scipy 1.16.3; statsmodels 0.14.5; matplotlib 3.10.6. Seeds [42, 123, 7]. Welch
  two-sample t-test; α = 0.05; |d| ≥ 0.5; 50 genes (20 panel + 30 null). CLAUDE.md
  reproducibility standards satisfied.

## 5. CRITICAL honesty — what this does and does NOT establish

**This validates the analysis LOOP and the statistical machinery, NOT the biology.**
The data are synthetic (`SYNTHETIC_DATA = True` on all rows) with effects planted by
hand in `config.yaml`. The experiment shows that, given known differential-expression
truth, the pipeline recovers the planted genes with high power, estimates effect sizes
ordered with planted magnitudes, suppresses true nulls, and applies Bonferroni + BH
corrections that behave as theory predicts. That is a *methods/infrastructure*
validation.

**It is NOT evidence for the "type 3 diabetes" / shared-mechanism model.** No real T2D
or AD tissue was analyzed. Significance here is a property of the injected signal, not
clinical reality. Do not report any biological conclusion from H001.

**What changes when a real GEO brain-tissue AD series is swapped in (same panel/test):**
- **Unknown ground truth** — no `planted` column; power/FDR can only be estimated. 100%
  recovery will not recur.
- **Batch / technical effects** — platform, RIN, post-mortem interval, brain region,
  site. Welch t-tests without adjustment mis-calibrate; batch correction (ComBat) or
  covariate modeling becomes mandatory.
- **Covariates** — age, sex, APOE genotype, PMI, cell-type composition. Move to a linear
  model (limma/DESeq2-style) with covariates.
- **Genome-wide multiple testing** — ~20k genes, not 50; and panel selection via KG
  overlap is itself a hypothesis-generating filter (conditional/circular concern).
- **Effect sizes** — real transcriptomic shifts are typically |d| < 0.3, so the |d| ≥
  0.5 bar is likely unrealistic and should be revisited.
- **Distributional assumptions & non-independence** — heavier tails, dropout,
  mean-variance dependence; repeated samples per subject/region need mixed-effects.

## Flags
- Data are synthetic with hand-planted effects — verdict applies to pipeline validation
  only, not biology (primary flag).
- One expected BH false positive (NULL_GENE_008, seed 7) — consistent with FDR.
- Success threshold |d| ≥ 0.5 is clearable on synthetic data but likely too strict for
  real expression data; revisit before real-data application.
- Statistical significance here is by construction; not clinical/practical significance.

## Recommended next steps
1. Swap in a real GEO AD brain-tissue series using the same panel/test as a *template*,
   but upgrade to a covariate-adjusted, batch-corrected model before any biological
   inference.
2. Re-derive a realistic effect-size expectation from literature; relax |d| accordingly.
3. Pre-register the multiple-testing scope (panel-restricted vs genome-wide).

## Summary

**SUCCESS METRIC MET — REJECT H₀ / SUPPORT H₁, on synthetic data only.** All 7 planted
genes (incl. the 5 central IDE/IAPP/INS/APOE/AKT1) recovered at BH-FDR < 0.05 with
|d| ≥ 0.5 across all 3 seeds; effect sizes track planted magnitudes; exactly 1 expected
BH false positive across 90 null tests (Bonferroni correctly rejected it). This
validates the **analysis loop and statistical machinery**, not T2D/AD biology — no
biological weight until a real, covariate-adjusted, batch-corrected series is analyzed.

*Evaluation by the results-evaluator agent (read-only); persisted here by the orchestrator.*
