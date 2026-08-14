"""
experiments/H001/run.py

Experiment H001: Differential expression of T2D–AD shared genes in
Alzheimer's brain tissue.

This script:
  1. Generates a CLEARLY-LABELED SYNTHETIC expression dataset with KNOWN
     planted differential-expression effects on a mechanistically-central
     subset of the T2D–AD shared-gene panel. The remaining panel genes and
     all added null genes have NO effect (ground truth = not significant).
  2. For each seed in config.yaml: runs per-gene Welch's t-tests (AD cases
     vs controls), applies Bonferroni AND Benjamini-Hochberg FDR correction
     over the full tested gene set, and computes Cohen's d per gene.
  3. Aggregates all per-gene-per-seed results into results/metrics.csv.
  4. Saves a volcano plot (Cohen's d vs -log10 BH p-value, planted genes
     highlighted) to results/figures/ as both .png and .pdf.
  5. Logs all reproducibility metadata to logs/run.log via the shared
     src/utils/log_run_metadata helper.
  6. Prints a concise per-gene stability summary (no interpretation).

Usage (from project root):
    python experiments/H001/run.py

All settings are read from experiments/H001/config.yaml.
No file paths, seeds, or parameters are hardcoded in this script.
"""

import os
import sys
import logging
import warnings
import pathlib

import yaml
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
import matplotlib
matplotlib.use("Agg")           # non-interactive backend for saving figures
import matplotlib.pyplot as plt
import seaborn as sns

# ---------------------------------------------------------------------------
# Resolve project root and add src/ to the import path
# ---------------------------------------------------------------------------
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.log_run_metadata import log_run_metadata
import tool_ledger
import validity


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(config_path: pathlib.Path) -> dict:
    """Load and return the config.yaml as a plain dict."""
    with open(config_path, "r") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------

def setup_logger(log_path: pathlib.Path) -> logging.Logger:
    """
    Configure a logger that writes to both stdout and a log file.
    The log file is created (with parent dirs) if it does not exist.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("H001")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False        # don't double-log via the root logger
    if logger.handlers:             # idempotent: don't stack handlers on re-call
        return logger

    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                             datefmt="%Y-%m-%dT%H:%M:%SZ")

    # File handler
    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Stdout handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # Route Python warnings to the logger
    logging.captureWarnings(True)
    warnings.filterwarnings("always")

    return logger


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

def generate_synthetic_expression(
    gene_panel: list,
    planted_effects: dict,
    n_control_genes: int,
    n_cases: int,
    n_controls: int,
    baseline_mean: float,
    baseline_std: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Generate a SYNTHETIC gene-expression dataset with KNOWN ground truth.

    Columns: sample_id, group (AD | control), SYNTHETIC_DATA=True marker,
             then one column per gene (log-normal expression values).

    Planted genes receive an additive shift (in log-space) applied to the
    AD-case group only. All other genes are drawn from the same distribution
    in both groups — ground truth: NOT differentially expressed.

    Parameters
    ----------
    gene_panel : list of str
        The 20 T2D-AD shared genes from config.
    planted_effects : dict
        Mapping of gene -> additive log-space shift for AD cases (ground truth).
    n_control_genes : int
        Number of extra null genes to append, making multiple-testing realistic.
    n_cases, n_controls : int
        Sample sizes per group.
    baseline_mean, baseline_std : float
        Log-normal parameters shared across all genes as the baseline.
    rng : np.random.Generator
        Seeded random number generator for reproducibility.

    Returns
    -------
    pd.DataFrame
        Shape (n_cases + n_controls) x (3 + n_genes_total).
        Columns: sample_id, group, SYNTHETIC_DATA, <gene1>, <gene2>, ...
    """
    n_samples = n_cases + n_controls
    groups = (["AD_case"] * n_cases) + (["control"] * n_controls)
    is_case = np.array([1] * n_cases + [0] * n_controls, dtype=bool)

    # Build the full gene list: panel genes + null control genes
    null_gene_names = [f"NULL_GENE_{i:03d}" for i in range(n_control_genes)]
    all_genes = gene_panel + null_gene_names

    expression = {}

    for gene in all_genes:
        # Baseline expression drawn from normal distribution in log-space
        # (equivalent to log-normal expression — standard in RNA-seq modeling)
        base_expr = rng.normal(loc=baseline_mean, scale=baseline_std, size=n_samples)

        # Apply planted effect only to AD cases, only for genes in planted_effects
        if gene in planted_effects:
            effect = planted_effects[gene]
            base_expr[is_case] += effect

        expression[gene] = base_expr

    df = pd.DataFrame(expression)
    df.insert(0, "group", groups)
    df.insert(0, "sample_id", [f"SAMPLE_{i:04d}" for i in range(n_samples)])

    # Clearly label this as synthetic data with known ground truth
    df.insert(2, "SYNTHETIC_DATA", True)
    df.insert(3, "KNOWN_GROUND_TRUTH",
              "planted_effect_genes_listed_in_config_planted_effects")

    return df


# ---------------------------------------------------------------------------
# Statistical testing (one seed at a time)
# ---------------------------------------------------------------------------

def cohens_d(group1: np.ndarray, group2: np.ndarray) -> float:
    """
    Compute Cohen's d for two independent groups.

    Uses the pooled standard deviation (equal-n formula generalizes cleanly;
    for unequal n the pooled SD is used).

    Returns a signed value: positive means group1 > group2.
    """
    n1, n2 = len(group1), len(group2)
    mean1, mean2 = group1.mean(), group2.mean()
    var1, var2 = group1.var(ddof=1), group2.var(ddof=1)

    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

    if pooled_std == 0.0:
        return 0.0

    return (mean1 - mean2) / pooled_std


def run_differential_expression(
    expr_df: pd.DataFrame,
    gene_columns: list,
    planted_effects: dict,
    alpha: float,
) -> pd.DataFrame:
    """
    Run per-gene Welch's t-tests between AD cases and controls.

    Collects raw p-values across all genes, then applies BOTH:
      - Bonferroni correction
      - Benjamini-Hochberg (BH) FDR correction
    via statsmodels multipletests over the full tested gene set.

    Parameters
    ----------
    expr_df : pd.DataFrame
        The expression table (must contain 'group' column).
    gene_columns : list of str
        Column names to test (panel genes + null genes).
    planted_effects : dict
        Ground-truth mapping — used only to label the 'planted' column.
    alpha : float
        Significance threshold for the 'significant_bh' flag.

    Returns
    -------
    pd.DataFrame
        One row per gene with columns:
        gene, mean_case, mean_ctrl, cohens_d, p_raw,
        p_bonferroni, p_bh, planted, significant_bh
    """
    case_df = expr_df[expr_df["group"] == "AD_case"]
    ctrl_df = expr_df[expr_df["group"] == "control"]

    records = []
    for gene in gene_columns:
        case_vals = case_df[gene].values
        ctrl_vals = ctrl_df[gene].values

        # Welch's t-test (equal_var=False)
        t_stat, p_raw = stats.ttest_ind(case_vals, ctrl_vals, equal_var=False)
        d = cohens_d(case_vals, ctrl_vals)

        records.append({
            "gene":       gene,
            "mean_case":  case_vals.mean(),
            "mean_ctrl":  ctrl_vals.mean(),
            "cohens_d":   d,
            "p_raw":      p_raw,
        })

    result_df = pd.DataFrame(records)
    raw_pvals = result_df["p_raw"].values

    # --- Bonferroni correction ---
    reject_bonf, p_bonf, _, _ = multipletests(raw_pvals, alpha=alpha,
                                              method="bonferroni")

    # --- Benjamini-Hochberg FDR correction ---
    reject_bh, p_bh, _, _ = multipletests(raw_pvals, alpha=alpha,
                                           method="fdr_bh")

    result_df["p_bonferroni"]  = p_bonf
    result_df["p_bh"]          = p_bh
    result_df["planted"]       = result_df["gene"].isin(planted_effects.keys())
    result_df["significant_bh"] = result_df["p_bh"] < alpha

    return result_df


# ---------------------------------------------------------------------------
# Volcano plot
# ---------------------------------------------------------------------------

def save_volcano_plot(
    metrics_df: pd.DataFrame,
    figures_dir: pathlib.Path,
    effect_threshold: float,
    alpha: float,
) -> None:
    """
    Save a volcano plot of Cohen's d vs -log10(BH-corrected p-value).

    Points are colored by:
      - Planted + significant: coral / highlighted
      - Not planted but significant: orange (unexpected positives)
      - Not significant: grey

    Planted genes are additionally annotated with gene labels.

    Both .png and .pdf are saved.

    Parameters
    ----------
    metrics_df : pd.DataFrame
        Aggregated per-gene-per-seed results; averaged across seeds for plotting.
    figures_dir : pathlib.Path
        Directory to write the figure files.
    effect_threshold : float
        |Cohen's d| threshold line to draw on the plot.
    alpha : float
        BH p-value threshold (shown as a horizontal dashed line).
    """
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Average across seeds for the plot
    agg = (
        metrics_df
        .groupby("gene", as_index=False)
        .agg(
            mean_d=("cohens_d", "mean"),
            mean_p_bh=("p_bh", "mean"),
            planted=("planted", "first"),
        )
    )
    agg["neg_log10_p_bh"] = -np.log10(agg["mean_p_bh"].clip(lower=1e-300))

    fig, ax = plt.subplots(figsize=(10, 7))

    # Background: non-planted, non-significant
    mask_bg = ~agg["planted"] & ~(agg["mean_p_bh"] < alpha)
    ax.scatter(
        agg.loc[mask_bg, "mean_d"],
        agg.loc[mask_bg, "neg_log10_p_bh"],
        color="lightgrey", alpha=0.6, s=30, label="Null gene (not sig.)",
        zorder=1,
    )

    # Unexpected significant (not planted but p_bh < alpha)
    mask_fp = ~agg["planted"] & (agg["mean_p_bh"] < alpha)
    ax.scatter(
        agg.loc[mask_fp, "mean_d"],
        agg.loc[mask_fp, "neg_log10_p_bh"],
        color="orange", alpha=0.85, s=50,
        label="Not planted but significant (FP candidate)", zorder=2,
    )

    # Planted genes
    mask_plant = agg["planted"]
    ax.scatter(
        agg.loc[mask_plant, "mean_d"],
        agg.loc[mask_plant, "neg_log10_p_bh"],
        color="crimson", edgecolors="black", linewidths=0.6,
        s=90, zorder=3, label="Planted (ground truth DE)",
    )

    # Gene labels for planted genes
    for _, row in agg[mask_plant].iterrows():
        ax.annotate(
            row["gene"],
            xy=(row["mean_d"], row["neg_log10_p_bh"]),
            xytext=(5, 4), textcoords="offset points",
            fontsize=8, color="darkred",
        )

    # Reference lines
    ax.axhline(-np.log10(alpha), color="steelblue", linestyle="--",
               linewidth=1.0, label=f"BH FDR = {alpha}")
    ax.axvline(effect_threshold, color="green", linestyle=":",
               linewidth=1.0, label=f"|d| = {effect_threshold}")
    ax.axvline(-effect_threshold, color="green", linestyle=":",
               linewidth=1.0)
    ax.axvline(0, color="black", linewidth=0.5, alpha=0.4)

    ax.set_xlabel("Cohen's d (AD case − control, mean across seeds)", fontsize=11)
    ax.set_ylabel("-log10(BH-corrected p-value, mean across seeds)", fontsize=11)
    ax.set_title(
        "H001: T2D–AD Shared Gene Panel — Differential Expression\n"
        "[SYNTHETIC DATA WITH KNOWN PLANTED EFFECTS]",
        fontsize=12, fontweight="bold",
    )
    ax.legend(fontsize=8, loc="upper left")
    sns.despine(ax=ax)

    fig.tight_layout()

    for ext in ("png", "pdf"):
        out_path = figures_dir / f"volcano.{ext}"
        fig.savefig(out_path, dpi=150)

    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # -----------------------------------------------------------------------
    # 0. Paths and config
    # -----------------------------------------------------------------------
    config_path = PROJECT_ROOT / "experiments" / "H001" / "config.yaml"
    cfg = load_config(config_path)

    log_path     = PROJECT_ROOT / cfg["outputs"]["log_file"]
    metrics_path = PROJECT_ROOT / cfg["outputs"]["metrics_csv"]
    figures_dir  = PROJECT_ROOT / cfg["outputs"]["figures_dir"]
    data_out     = PROJECT_ROOT / cfg["data"]["synthetic_output_path"]

    # Ensure output directories exist
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    data_out.parent.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # 1. Logger + reproducibility header
    # -----------------------------------------------------------------------
    logger = setup_logger(log_path)
    seeds  = cfg["seeds"]
    log_run_metadata(logger, seeds, phase="start")

    logger.info(f"Config loaded from: {config_path}")
    logger.info(f"Project root: {PROJECT_ROOT}")

    # -----------------------------------------------------------------------
    # 2. Extract config values
    # -----------------------------------------------------------------------
    gene_panel      = cfg["gene_panel"]
    planted_effects = cfg["planted_effects"]
    n_control_genes = cfg["synthetic"]["n_control_genes"]
    n_cases         = cfg["synthetic"]["n_cases"]
    n_controls      = cfg["synthetic"]["n_controls"]
    baseline_mean   = cfg["synthetic"]["baseline_mean"]
    baseline_std    = cfg["synthetic"]["baseline_std"]
    alpha           = cfg["statistics"]["alpha"]
    effect_thresh   = cfg["statistics"]["effect_size_threshold"]

    # All genes that will be tested (panel + null)
    null_gene_names = [f"NULL_GENE_{i:03d}" for i in range(n_control_genes)]
    all_tested_genes = gene_panel + null_gene_names

    n_total_genes = len(all_tested_genes)

    # Experiment tool ledger: record the scientific/statistical operations this
    # experiment actually performs, in order -> experiments/H001/tool_ledger.json.
    led = tool_ledger.ToolLedger(task="H001 differential-expression experiment",
                                 run_id="H001", experiment_id="H001")
    logger.info(f"Panel genes: {len(gene_panel)} | Null genes: {n_control_genes} "
                f"| Total tested: {n_total_genes}")
    logger.info(f"Planted-effect genes: {list(planted_effects.keys())}")

    # -----------------------------------------------------------------------
    # 3. Generate synthetic dataset (use first seed so it is deterministic)
    #    The same baseline dataset is regenerated inside each seed loop below
    #    so each seed produces an independent synthetic draw. This tests
    #    stability of detection across different random realizations.
    #
    # Also save one canonical copy (seed=seeds[0]) to data/processed/ for
    # downstream inspection. Clearly labeled as SYNTHETIC.
    # -----------------------------------------------------------------------
    logger.info("Generating canonical synthetic dataset (seed=%d) ...", seeds[0])
    rng_canonical = np.random.default_rng(seeds[0])
    canonical_df  = generate_synthetic_expression(
        gene_panel=gene_panel,
        planted_effects=planted_effects,
        n_control_genes=n_control_genes,
        n_cases=n_cases,
        n_controls=n_controls,
        baseline_mean=baseline_mean,
        baseline_std=baseline_std,
        rng=rng_canonical,
    )
    canonical_df.to_csv(data_out, index=False)
    led.record("generate_synthetic_expression",
               {"seed": seeds[0], "canonical": True, "n_genes": n_total_genes}, "experiment")

    # Pre-registered validity gates (hypothesis-orthogonal machinery checks).
    gates = validity.Gates(logger)
    vg = cfg.get("validity_gates", {})
    if "cohort_integrity" in vg:
        g = vg["cohort_integrity"]
        gates.cohort_integrity({"AD": n_cases, "control": n_controls},
                               g["min_per_arm"], g.get("severity", "halt"))
    if "data_scale" in vg:
        g = vg["data_scale"]
        gene_cols_c = [c for c in canonical_df.columns
                       if c not in ("sample_id", "group", "SYNTHETIC_DATA", "KNOWN_GROUND_TRUTH")]
        gates.data_scale(canonical_df[gene_cols_c].to_numpy().ravel(),
                         g.get("kind", "log"), g["max_expected"], g.get("severity", "halt"))
    logger.info(f"Synthetic dataset saved to: {data_out} "
                f"(shape: {canonical_df.shape})")
    logger.info("NOTE: SYNTHETIC_DATA column = True for all rows. "
                "Columns SYNTHETIC_DATA and KNOWN_GROUND_TRUTH are metadata "
                "markers — not gene expression values.")

    # -----------------------------------------------------------------------
    # 4. Multi-seed differential expression loop
    # -----------------------------------------------------------------------
    all_results = []

    for seed in seeds:
        logger.info(f"--- Seed {seed}: generating independent synthetic draw ---")
        rng = np.random.default_rng(seed)
        expr_df = generate_synthetic_expression(
            gene_panel=gene_panel,
            planted_effects=planted_effects,
            n_control_genes=n_control_genes,
            n_cases=n_cases,
            n_controls=n_controls,
            baseline_mean=baseline_mean,
            baseline_std=baseline_std,
            rng=rng,
        )

        # Drop metadata columns before testing — only test gene columns
        gene_cols = [c for c in expr_df.columns
                     if c not in ("sample_id", "group",
                                  "SYNTHETIC_DATA", "KNOWN_GROUND_TRUTH")]

        logger.info(f"  Running Welch t-tests on {len(gene_cols)} genes ...")
        led.record("generate_synthetic_expression", {"seed": seed, "n_genes": len(gene_cols)}, "experiment")
        results = run_differential_expression(
            expr_df=expr_df,
            gene_columns=gene_cols,
            planted_effects=planted_effects,
            alpha=alpha,
        )
        # the scientific ops run_differential_expression performs, in order:
        led.record("scipy.stats.ttest_ind", {"variant": "welch", "genes": len(gene_cols), "seed": seed}, "experiment")
        led.record("cohens_d", {"genes": len(gene_cols), "seed": seed}, "experiment")
        led.record("statsmodels.multipletests", {"method": "bonferroni", "seed": seed}, "experiment")
        led.record("statsmodels.multipletests", {"method": "fdr_bh", "seed": seed}, "experiment")

        results["seed"] = seed
        n_sig_bh   = results["significant_bh"].sum()
        n_planted_sig = (results["significant_bh"] & results["planted"]).sum()

        logger.info(f"  Seed {seed}: {n_sig_bh} genes significant at BH-FDR<{alpha} "
                    f"(of which {n_planted_sig} are planted)")

        all_results.append(results)

    # -----------------------------------------------------------------------
    # 5. Aggregate and save metrics.csv
    # -----------------------------------------------------------------------
    metrics_df = pd.concat(all_results, ignore_index=True)

    # Reorder columns to match the spec
    ordered_cols = [
        "gene", "seed", "mean_case", "mean_ctrl",
        "cohens_d", "p_raw", "p_bonferroni", "p_bh",
        "planted", "significant_bh",
    ]
    metrics_df = metrics_df[ordered_cols]
    metrics_df.to_csv(metrics_path, index=False)

    # Negative-control gate: the NULL_GENE_* set has no planted effect and should stay
    # null (validates FDR control — orthogonal to the planted/hypothesis genes).
    if "negative_control" in vg:
        g = vg["negative_control"]
        null_rows = metrics_df[metrics_df["gene"].str.startswith("NULL_GENE")]
        frac = float(null_rows["significant_bh"].mean()) if len(null_rows) else 0.0
        gates.negative_control("NULL_GENE_set", frac, g["max_frac_significant"], g.get("severity", "flag"))
    gates.save(PROJECT_ROOT / "experiments" / "H001" / "validity.json")
    logger.info(gates.summary())
    logger.info(f"Metrics saved to: {metrics_path} "
                f"(rows: {len(metrics_df)}, columns: {list(metrics_df.columns)})")

    # -----------------------------------------------------------------------
    # 6. Volcano plot
    # -----------------------------------------------------------------------
    logger.info("Saving volcano plot ...")
    save_volcano_plot(
        metrics_df=metrics_df,
        figures_dir=figures_dir,
        effect_threshold=effect_thresh,
        alpha=alpha,
    )
    led.record("matplotlib.savefig", {"artifact": "volcano", "formats": ["png", "pdf"]}, "experiment")
    ledger_path = led.save(PROJECT_ROOT / "experiments" / "H001" / "tool_ledger.json")
    logger.info(f"Figures saved to: {figures_dir}/volcano.{{png,pdf}}")
    logger.info(f"Tool ledger (scientific ops) saved to: {ledger_path}")

    # -----------------------------------------------------------------------
    # 7. Per-gene stability summary (printed only — no interpretation)
    # -----------------------------------------------------------------------
    success_genes = (
        metrics_df
        .groupby("gene")
        .apply(
            lambda g: pd.Series({
                "planted":          g["planted"].iloc[0],
                "n_seeds":          len(g),
                "seeds_sig_bh":     int(g["significant_bh"].sum()),
                "seeds_large_d":    int((g["cohens_d"].abs() >= effect_thresh).sum()),
                "seeds_pass_both":  int(
                    (g["significant_bh"] & (g["cohens_d"].abs() >= effect_thresh)).sum()
                ),
                "mean_d":           round(g["cohens_d"].mean(), 4),
                "mean_p_bh":        round(g["p_bh"].mean(), 6),
            })
        )
        .reset_index()
    )

    print("\n" + "=" * 72)
    print("H001 STABILITY SUMMARY (no interpretation — for results-evaluator)")
    print(f"Success criterion: BH-FDR < {alpha} AND |Cohen's d| >= {effect_thresh}, "
          f"across {len(seeds)} seeds")
    print("=" * 72)

    passing = success_genes[success_genes["seeds_pass_both"] == len(seeds)]
    print(f"\nGenes passing success criterion in ALL {len(seeds)} seeds "
          f"(n={len(passing)}):")
    if len(passing) > 0:
        print(passing[["gene", "planted", "mean_d", "mean_p_bh",
                        "seeds_pass_both"]].to_string(index=False))
    else:
        print("  (none)")

    partially = success_genes[
        (success_genes["seeds_pass_both"] > 0) &
        (success_genes["seeds_pass_both"] < len(seeds))
    ]
    print(f"\nGenes passing in SOME but not all seeds (n={len(partially)}):")
    if len(partially) > 0:
        print(partially[["gene", "planted", "mean_d", "mean_p_bh",
                          "seeds_pass_both"]].to_string(index=False))
    else:
        print("  (none)")

    print(f"\nTotal genes tested: {n_total_genes} "
          f"({len(gene_panel)} panel + {n_control_genes} null)\n")

    # -----------------------------------------------------------------------
    # 8. End-of-run metadata
    # -----------------------------------------------------------------------
    log_run_metadata(logger, seeds, phase="end")


if __name__ == "__main__":
    main()
