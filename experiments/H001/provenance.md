# Provenance — H001: Differential expression of T2D–AD shared genes in Alzheimer's brain tissue

*Assembled by `provenance.py` from the experiment's own artifacts (deterministic, no LLM). One view of how the hypothesis was formed and tested.*

## Hypothesis (how it was framed)
- **Question:** Do genes shared between Type 2 Diabetes Mellitus and Alzheimer's Disease (surfaced via biomedical knowledge-graph overlap) show differential expression between AD cases and controls in brain tissue, detectable above multiple-testing correction — supporting the shared-mechanism / 'type 3 diabetes' model?
- **H₀:** H₀: None of the T2D–AD shared-gene panel show differential expression between AD cases and controls beyond chance; no shared gene reaches BH-FDR < 0.05 with |Cohen's d| ≥ 0.5.
- **H₁:** H₁: A subset of the T2D–AD shared-gene panel is differentially expressed between AD cases and controls, with ≥3 genes significant at BH-FDR < 0.05 and |Cohen's d| ≥ 0.5, consistent with a shared insulin-resistance / brain-metabolism mechanism.
- **Success metric:** ≥3 of the planted-effect shared genes are significant at BH-FDR < 0.05 with |Cohen's d| ≥ 0.5, reproducibly across ≥3 independent seeds. Report both Bonferroni- and BH-corrected p-values and Cohen's d for every gene in the panel.
- **Status:** approved · created 2026-08-13

## Formation — how the hypothesis was formed
- **Method:** Per-gene case/control differential expression test across the shared-gene panel: for each gene, compare AD-case vs control expression (two-sample test, e.g. Welch's t-test), collect raw p-values across the panel, then apply BOTH Bonferroni and Benjamini-Hochberg FDR correction over the number of genes tested. Report per-gene effect size (Cohen's d) alongside corrected p-values. Repeat across ≥3 independent seeds (synthetic-data regeneration / resampling) and summarize stability of the significant-gene set.
- **Data source:** data/processed/synthetic_ad_expression.csv
- **Formation tool trace:** not linked (hypothesis predates the tool ledger, or was formalized directly); reasoning captured in the spec above.

## Testing — how it was tested
- **Design:** 20-gene panel; seeds=[42, 123, 7]
- **Scientific tool calls (in order, 17):**
  1. generate_synthetic_expression
  2. generate_synthetic_expression
  3. scipy.stats.ttest_ind (welch)
  4. cohens_d
  5. statsmodels.multipletests (bonferroni)
  6. statsmodels.multipletests (fdr_bh)
  7. generate_synthetic_expression
  8. scipy.stats.ttest_ind (welch)
  9. cohens_d
  10. statsmodels.multipletests (bonferroni)
  11. statsmodels.multipletests (fdr_bh)
  12. generate_synthetic_expression
  13. scipy.stats.ttest_ind (welch)
  14. cohens_d
  15. statsmodels.multipletests (bonferroni)
  16. statsmodels.multipletests (fdr_bh)
  17. matplotlib.savefig (volcano)
- **Statistical standards:** Bonferroni + BH-FDR, effect sizes, ≥3 runs/robustness checks, reproducibility log.

## Result
- **Metrics:** metrics.csv (150 rows)
- **Verdict:** **SUCCESS METRIC MET — REJECT H₀ / SUPPORT H₁, on synthetic data only.** All 7 planted genes (incl. the 5 central IDE/IAPP/INS/APOE/AKT1) recovered at BH-FDR < 0.05 with |d| ≥ 0.5 across all 3 seeds; effect sizes track planted magnitudes; exactly 1 expected BH false positive across 90 null tests (Bonferroni correctly rejected it). This validates the **analysis loop and statistical machinery**, not T2D/AD biology — no biological weight until a real, covariate-adjusted, batch-corrected series is analyzed. *Evaluation by the results-evaluator agent (read-only); persisted here by the orchestrator.

## Audit trail
- spec: `hypotheses/H001_t2d_ad_shared_genes.yaml`
- config: `experiments/H001/config.yaml`
- tool ledger (scientific ops): `experiments/H001/tool_ledger.json`
- metrics: `experiments/H001/results/`
- evaluation: `reports/H001_evaluation.md`
- run log: `experiments/H001/logs/run.log`
