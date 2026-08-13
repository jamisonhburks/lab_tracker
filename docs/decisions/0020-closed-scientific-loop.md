# ADR-0020: Close the scientific loop (generate → formalize → implement → run → evaluate)

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
The system had become a strong hypothesis *generator + triager* (KG-constrained
generation, novelty flag, refinement loop) but never **tested** a hypothesis. CLAUDE.md
already defines the downstream pipeline — `hypothesis-planner → code-implementer →
experiment-runner → results-evaluator`, with `hypotheses/`, `experiments/{id}/`, and
project statistical standards — but it was unwired. With the Claude specialist in place
(ADR-0019), closing the loop was finally feasible.

## Decision
Orchestrate the four specialist agents in sequence, seeded by the agent's own KG
hypothesis, producing the full artifact chain and enforcing **separation of concerns**
(the anti-self-confirmation property from ADR-0011):
- **hypothesis-planner** → writes/approves `hypotheses/H{NNN}_*.yaml` (does not code).
- **code-implementer** → writes `experiments/{id}/` (config.yaml, run.py) (does not run).
- **experiment-runner** → executes run.py, logs metadata (does not interpret).
- **results-evaluator** → interprets metrics vs the spec, read-only (does not re-run).

Because this toy repo has no real cohort, the first pass runs on a **clearly-labeled
synthetic dataset with known planted ground truth** — validating the machinery before
any real-data claim. A real GEO series swaps in via the data path.

## Rationale & evidence — H001 end-to-end
Carried the T2D↔Alzheimer's shared-gene thread through the loop:
- **Spec**: `H001_t2d_ad_shared_genes.yaml` — differential expression of the 20 KG-shared
  genes, BH-FDR < 0.05 & |Cohen's d| ≥ 0.5, ≥3 seeds.
- **Ran** in ~3s: 50 genes (20 panel + 30 null), Welch t-test, **Bonferroni AND BH**,
  Cohen's d, 3 seeds, volcano plot, reproducibility log.
- **Result**: recovered **7/7 planted** genes (incl. the 5 central IDE/IAPP/INS/APOE/
  AKT1) at BH-FDR < 0.05 & |d| ≥ 0.5 in all 3 seeds; effect sizes tracked planted
  magnitudes; **1 expected BH false positive** across 90 null tests (Bonferroni
  correctly rejected it) — textbook FDR behavior.
- **Evaluation** (`reports/H001_evaluation.md`): REJECT H₀ *on the synthetic benchmark
  only*. The evaluator was explicit that this validates the **loop + statistics**, not
  the biology, and enumerated what changes for real data (batch effects, covariates,
  genome-wide multiple testing, realistic — much smaller — effect sizes).
- **Feedback loop worked**: the evaluator caught a real duplicate-logging defect; it was
  fixed (`propagate=False` + idempotent handler guard) and re-verified.

## Consequences
- The system now closes **generate → test → interpret**, not just generate.
- Separation of concerns is enforced by the agents' tool sets (e.g. results-evaluator is
  read-only), structurally preventing the generator from grading its own work.
- Synthetic-first is the honest default: it proves error control against known truth.
  Real inference requires the upgrades the evaluator listed — do NOT report biology from
  a synthetic run.
- `experiments/*/results/figures/` and `logs/` are gitignored (regenerable); `metrics.csv`,
  code, spec, and the evaluation report are tracked for audit.
