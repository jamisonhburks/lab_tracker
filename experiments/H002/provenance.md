# Provenance — H002: Differential expression of T2D–AD shared genes in REAL human brain tissue, prep-matched bulk-vs-bulk cross-dataset replication

*Assembled by `provenance.py` from the experiment's own artifacts (deterministic, no LLM). One view of how the hypothesis was formed and tested.*

## Hypothesis (how it was framed)
- **Question:** Are the T2D–AD knowledge-graph shared genes (especially the mechanistically central IDE, IAPP, INS, APOE, AKT1) differentially expressed between Alzheimer's cases and controls in real human bulk brain tissue, after adjusting for covariates (age, sex, brain region) and multiple testing, with direction replication in an independent, preparation-matched, region-matched bulk-tissue dataset?
- **H₀:** H₀: After covariate adjustment and panel-restricted multiple-testing correction, none of the central T2D–AD shared genes (IDE, IAPP, INS, APOE, AKT1) is differentially expressed between AD cases and age-matched cognitively-normal controls at BH-FDR < 0.05 in GSE48350 (bulk tissue), or any nominal signal fails to replicate in direction (same sign, p < 0.05) in the FRONTAL cortex of GSE122063 (bulk tissue).
- **H₁:** H₁: At least one central T2D–AD shared gene (especially IDE or APOE) is differentially expressed between AD cases and age-matched normal controls at BH-FDR < 0.05 in GSE48350 (diagnosis coefficient in the covariate-adjusted linear model) AND replicates in direction (same sign, nominal p < 0.05) in the FRONTAL cortex of the independent bulk-tissue dataset GSE122063, consistent with a shared insulin-resistance / brain-metabolism mechanism.
- **Success metric:** ≥1 of the central shared genes (especially IDE or APOE) is differentially expressed at BH-FDR < 0.05 in GSE48350 (covariate-adjusted diagnosis coefficient) AND replicates in direction (same sign, nominal p < 0.05) in the FRONTAL cortex of GSE122063. Report standardized effect sizes with 95% CI and BOTH Bonferroni- and BH-corrected p-values for ALL 20 panel genes, plus the power assessment. Deliberately NO hard |Cohen's d| floor: real bulk brain-transcriptomic effects are frequently |d| < 0.3, so effect magnitude is reported with its CI rather than gated by a threshold (this relaxes H001's |d| ≥ 0.5 criterion, per the H001 evaluator's warning that it is too strict for real transcriptomics). Because the two platforms differ, replication requires only matched SIGN of the diagnosis effect, not matched magnitude.

- **Status:** approved · created 2026-08-13

## Formation — how the hypothesis was formed
- **Method:** Confirmatory, panel-restricted differential-expression analysis over the 20 T2D–AD KG-shared genes, prep-matched bulk-vs-bulk across two platforms: (1) Per-PLATFORM probe→gene collapse: map probes to gene symbols separately for GPL570 (GSE48350) and GPL16699 (GSE122063); where a gene maps to multiple probes, collapse to a single per-gene value using the max-variance probe WITHIN each platform (pre-registered rule; mean as documented fallback). The analysis panel is then aligned across datasets by GENE SYMBOL, not by probe ID. (2) Per-gene LINEAR MODEL (NOT a two-sample t-test) with covariates. Primary (GSE48350): expression ~ diagnosis (AD vs age-matched normal control) + age + sex + brain region. Report the diagnosis coefficient, its 95% CI, and a standardized effect size (partial Cohen's d / standardized beta) for every panel gene. (3) Two-sided tests per gene (per-gene direction largely unknown a priori). (4) Multiple testing: PANEL-RESTRICTED and pre-registered (confirmatory over the 20 genes, NOT genome-wide discovery). Apply BOTH Bonferroni and Benjamini-Hochberg FDR over the 20 panel p-values. Explicitly flag the KG-panel-selection caveat: inference is valid only within the panel and does not license genome-wide or causal claims. (5) Replication: any gene significant at BH-FDR < 0.05 in GSE48350 must replicate in DIRECTION (same sign of diagnosis coefficient) at nominal p < 0.05 in GSE122063, RESTRICTED TO FRONTAL cortex samples (superior frontal cortex ∩ frontal cortex). Because platforms differ, only the sign of the effect is required to match, not the magnitude. (6) Replication model (GSE122063, frontal cortex): expression ~ diagnosis (AD vs non-demented) + age + sex, on Agilent processed signal. (7) APOE caveat: microarray probes quantify APOE mRNA and cannot distinguish ε2/ε3/ε4 alleles; APOE genotype is NOT available here, so any APOE signal is transcript-level and must not be interpreted as an ε4 dosage / genotype effect. Flag prominently in reporting. (8) Power check: report an a-priori/post-hoc power assessment for the primary GSE48350 analysis (given per-region n after age-matching) to detect the small transcriptomic effects typical of bulk brain (|d| ~ 0.2–0.4), so null findings can be interpreted against achievable power rather than assumed conclusive.

- **Data source:** data/external/GSE48350 (primary; bulk tissue, GPL570 Affymetrix); data/external/GSE122063 (replication; bulk tissue, frontal cortex, GPL16699 Agilent)
- **Pre-registered decisions:** design, multiple_testing_scope, region_restriction, test_directionality, covariate_set, probe_collapse_method, effect_size_reporting, replication_rule, apoe_genotype_caveat, power_check, robustness_checks
- **Formation tool trace:** not linked (hypothesis predates the tool ledger, or was formalized directly); reasoning captured in the spec above.

## Testing — how it was tested
- **Design:** 20-gene panel; primary=GSE48350; replication=GSE122063
- **Scientific tool calls (in order, 13):**
  1. GEOparse.get_GEO (GSE48350)
  2. collapse_probes_to_genes (max_variance)
  3. statsmodels.ols (GSE48350)
  4. statsmodels.multipletests (GSE48350)
  5. bootstrap_effect_size_ci (GSE48350)
  6. statsmodels.TTestIndPower
  7. run_per_region_robustness (GSE48350)
  8. GEOparse.get_GEO (GSE122063)
  9. collapse_tech_rep_expression (GSE122063)
  10. collapse_probes_to_genes (max_variance)
  11. statsmodels.ols (GSE122063)
  12. check_direction_replication
  13. matplotlib.savefig (forest_plot)
- **Statistical standards:** Bonferroni + BH-FDR, effect sizes, ≥3 runs/robustness checks, reproducibility log.

## Result
- **Metrics:** metrics.csv (39 rows), metrics_per_region.csv (57 rows), metrics_power.csv (3 rows), metrics_replication.csv (3 rows)
- **Verdict:** FAIL TO REJECT H₀** — no central shared gene is both BH-significant

## Audit trail
- spec: `hypotheses/H002_t2d_ad_shared_genes_realdata.yaml`
- config: `experiments/H002/config.yaml`
- tool ledger (scientific ops): `experiments/H002/tool_ledger.json`
- metrics: `experiments/H002/results/`
- evaluation: `reports/H002_evaluation.md`
- run log: `experiments/H002/logs/run.log`
