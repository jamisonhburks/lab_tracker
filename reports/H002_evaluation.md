# H002 Evaluation — T2D–AD Shared-Gene Differential Expression in Real Human Brain Tissue

**Experiment:** H002
**Hypothesis file:** `hypotheses/H002_t2d_ad_shared_genes_realdata.yaml`
**Design:** Prep-matched, region-matched bulk-vs-bulk. Primary GSE48350 (bulk, GPL570 Affymetrix); replication GSE122063 (bulk, GPL16699 Agilent), restricted to frontal cortex.
**Evaluated:** 2026-08-13
**Evaluator role:** results interpretation only (no re-run, no file modification).

---

## Runs completed / robustness checks

`min_runs: 3` was pre-registered as 3 robustness checks (not 3 stochastic seeds — OLS
on fixed real data is deterministic). All three executed: (1) within-GSE48350 per-region
consistency, (2) cross-dataset direction replication in GSE122063 frontal cortex, (3)
bootstrap 95% CIs on effect sizes (1000 iterations). The **binding limitation is
statistical power, not run count** (Section 4).

## 1. Verdict on the pre-registered success metric

**Metric:** ≥1 central shared gene (esp. IDE or APOE) at **BH-FDR < 0.05 in GSE48350**
AND **direction-replicates** (same sign, p < 0.05) **in GSE122063 frontal cortex.**

**Result: NOT MET. Fail to reject H₀.**

- No central gene reaches BH-FDR < 0.05 in GSE48350:
  - IDE +0.022 (p=0.766, p_bh=0.856); IAPP +0.022 (p=0.215, p_bh=0.340); INS +0.008
    (p=0.617, p_bh=0.835); AKT1 −0.003 (p=0.921, p_bh=0.923) — all null.
  - **APOE −0.283 (p=0.013, p_bh≈0.0539) — borderline, does NOT clear BH<0.05, sign DECREASED.**
- The discovery gate is never passed by a central gene, so the replication gate isn't
  reached for the central set.

APOE's p_bh≈0.054 must **not** be reported as significant — that would be
threshold-shopping against the pre-registration.

## 2. The three discovery-stage BH hits — all failed direction replication

| Gene | Primary coef | p_bh | Bonferroni | Replication coef | Rep p | Outcome |
|------|-------------|------|-----------|------------------|-------|---------|
| SOD1 | +0.143 | 0.017 | **0.017 (sig)** | −0.290 | 0.148 | wrong sign |
| PPARGC1A | +0.225 | 0.046 | 0.137 (ns) | −0.610 | 0.0022 | wrong sign |
| APP | +0.194 | 0.043 | 0.086 (ns) | −0.475 | 0.117 | wrong sign |

**These do NOT count as findings.** Direction replication was the pre-registered arbiter
against dataset/platform artifacts; all three flipped sign. PPARGC1A is *significantly
discordant* (opposite direction, rep p=0.0022). APP was not in the central set; only
SOD1 cleared Bonferroni in discovery — and it too failed to replicate.

## 3. The central genes in detail

- **IDE, INS, IAPP, AKT1:** null in the primary (all p_bh > 0.33; bootstrap CIs span zero).
- **APOE:** borderline DECREASED (p_bh≈0.054); same (negative) sign in replication but
  non-significant (−0.072, p=0.62), and the discovery gate was never passed. Per-region
  consistently negative but underpowered.

**INS/IAPP caveat:** insulin and amylin are canonically pancreatic; in *bulk* brain they
sit near array background, so their nulls mean "this modality can't meaningfully test
these genes," not "unrelated to AD."

**APOE mRNA-vs-genotype caveat:** the probe quantifies APOE *transcript*, not ε2/ε3/ε4
status. A transcript change is not an ε4-dosage effect; no genotype was available.

## 4. Power / non-replication ambiguity — CRITICAL, bounds every negative claim

The replication arm collapsed to **n = 23 (AD=12, control=11)** after excluding vascular
dementia + temporal cortex and collapsing technical replicates (50 GSMs → 23 subjects).
Pre-registered power table:

| |Cohen's d| | Power at α=0.05 |
|-----------|-----------------|
| 0.2 | 0.092 |
| 0.3 | 0.147 |
| 0.4 | 0.224 |

For the small effects typical of bulk brain transcriptomics (|d| ~ 0.2–0.4), **power is
9–22%.** So **non-replication is confounded with low power** — we cannot distinguish a
true null from a real small effect this arm could never detect. This bounds every
negative claim: the result does not license "these genes are unrelated to AD"
(underpowered), nor "a trend supports the hypothesis" (the gate was not passed and the
panel hits reversed sign).

## 5. Multiple-testing behavior and reproducibility / provenance

- Scope: panel-restricted, confirmatory, over the **19 testable genes** (ND1 untestable on
  GPL570). Correctly not genome-wide.
- **Bonferroni:** 1 significant (SOD1). **BH:** 3 (PPARGC1A, SOD1, APP). The gap is
  expected; the two BH-only hits sit near the FDR boundary and both failed replication.
- **Provenance (run.log):** Python 3.13.9; numpy 2.3.5, pandas 2.3.3, scipy 1.16.3,
  statsmodels 0.14.5, matplotlib 3.10.6; seed 42. Primary GSE48350 n=173 (**AD=33,
  control=140** — ~19% positive, class imbalance flagged; drives low per-region power).
  Replication GSE122063 n=23. Covariates: `diagnosis + age + sex + C(region)` (primary),
  `diagnosis + age + sex + pmi` (replication). **Diagnosis-coding fix:** GSE48350 codes AD
  as `AA`; the final clean run correctly retained AD=33 (traceable in the log).
  Technical replicates collapsed to subjects (non-independence handled). Post-central
  gyrus region dropped (n=0 after filtering); the pre-registered frontal region-match is
  intact.

## 6. Honest bottom line

**H002 does NOT provide evidence for the T2D–AD shared-gene differential-expression
hypothesis in bulk brain.** No central gene is BH-significant-and-replicated; APOE is
borderline, decreased, and not an ε4 readout; the three panel BH hits reversed sign.

**But this is an honest null, not a refutation.** With a replication arm of n≈23 (power
0.09–0.22), a true small effect would usually fail to replicate by chance. The correct
reading: *this design, at this sample size and in this modality, did not detect a
replicable shared-gene signal* — not *the genes are unrelated*.

**Contrast with H001:** H001 succeeded on **synthetic** data with injected effects and
adequate power by construction. H002 is the real-data counterpart and returns a
**null / non-replication** — the honest and *expected common outcome* moving from
synthetic to real bulk-brain transcriptomics (small effects, modest cohorts, cell-type
dilution). This is credibility-positive for the pipeline: pre-registration held,
corrections were applied, the replication gate did its job, and the negative was reported
without spin.

## 7. Recommended next steps

1. **Properly powered replication** — MSBB GSE84422 (n≈2,004), ROSMAP RNA-seq. At those n,
   |d|~0.2–0.3 is detectable, so non-replication would actually mean "true null."
2. **Pre-specify effect direction** where biology permits (e.g. APOE decrease) for a
   one-sided, higher-power replication.
3. **Cell-type-aware / single-nucleus data** (snRNA-seq: ROSMAP, SEA-AD) — bulk dilutes
   neuronal signal; likely the right resolution for an insulin-resistance mechanism.
4. **Revisit the modality for INS/IAPP** — near-absent in bulk brain; drop them or test in
   an appropriate tissue; restrict the brain analysis to plausibly brain-expressed nodes
   (IDE, AKT1, APOE, PPARGC1A).
5. **Tighter cohort/platform matching** to interpret sign reversals (e.g. PPARGC1A) as
   biology rather than technical confound.
6. **Report APOE only with the transcript-vs-genotype caveat.**

---

*One-line verdict:* **FAIL TO REJECT H₀** — no central shared gene is both BH-significant
in GSE48350 and direction-replicated (APOE borderline p_bh≈0.054, decreased); the three
panel BH hits (PPARGC1A, SOD1, APP) all reversed sign in replication; but with a
replication arm of n≈23 (power 0.09–0.22), this is an honest **underpowered real-data
null**, not evidence the genes are unrelated.

*Evaluation by the results-evaluator agent (read-only); persisted here by the orchestrator.*
