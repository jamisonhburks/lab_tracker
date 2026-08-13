"""
experiments/H002/run.py
=======================
H002 — T2D–AD shared-gene differential expression in real human bulk brain tissue.

Primary dataset  : GSE48350 (GPL570 Affymetrix, ~253 samples, 4 brain regions)
Replication      : GSE122063 (GPL16699 Agilent, ~136 samples, frontal + temporal cortex)

Flow summary
------------
1.  Load config.yaml.
2.  Configure logging → logs/run.log.
3.  Log reproducibility metadata (Python version, package versions, seed, timestamp).
4.  Fetch / cache GEO series matrices via GEOparse (data/external/geo/).
5.  Parse sample metadata per the pre-registered schema:
      GSE48350  : diagnosis from "individual: <id>, <DX>"; keep C / AD;
                  extract brain region, gender, age.
      GSE122063 : diagnosis from "patient diagnosis:"; keep AD + Control,
                  EXCLUDE Vascular dementia; keep frontal cortex only;
                  collapse _TechRep1/2 technical replicates by subject mean.
6.  Build per-platform expression matrices; probe→gene collapse (max-variance probe).
7.  Align panel genes by GENE SYMBOL across platforms.  Flag panel genes missing
    from either platform as untestable (written to results/metrics.csv).
8.  Fit per-gene OLS in GSE48350 (all regions):
      expr ~ C(diagnosis) + age + sex_male + C(region)
    Report diagnosis coefficient, 95 % CI, p-value, standardised beta.
9.  Apply panel-restricted multiple-testing corrections (Bonferroni + BH-FDR) over
    the 20 panel p-values from step 8.
10. Bootstrap CIs on standardised effect size (1 000 iterations) per gene.
11. Power assessment: report power to detect |d| ∈ {0.2, 0.3, 0.4} at alpha=0.05
    given the per-region n after keeping C / AD only.
12. Robustness check 1 — per-region OLS in GSE48350 (fit separately for each of
    the four brain regions; record per-region diagnosis coefficients).
13. Fit per-gene OLS in GSE122063 frontal cortex:
      expr ~ C(diagnosis) + age + sex_male + pmi
14. Cross-platform direction replication: for every gene significant at BH-FDR < 0.05
    in step 9, check that the diagnosis coefficient sign matches AND nominal p < 0.05
    in GSE122063 (step 13).  Record replication status per gene.
15. Build forest-plot figure: one row per panel gene, showing GSE48350 and GSE122063
    diagnosis coefficients ± 95 % CI side-by-side.  Save as .png and .pdf.
16. Save all results to results/metrics.csv.
17. Log end timestamp.

Usage
-----
    cd <project_root>
    python experiments/H002/run.py

All paths are resolved relative to the project root (directory containing this
script's grandparent).
"""

from __future__ import annotations

import logging
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Project root resolution — two levels up from this file
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.log_run_metadata import log_run_metadata  # noqa: E402


# ===========================================================================
# Section 1: Config helpers
# ===========================================================================

def load_config(config_path: Path) -> dict:
    with open(config_path, "r") as fh:
        return yaml.safe_load(fh)


def setup_logger(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("H002")
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_file, mode="a")
    fh.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                             datefmt="%Y-%m-%dT%H:%M:%SZ")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    # Redirect Python warnings into the logger
    logging.captureWarnings(True)
    warnings.simplefilter("always")

    return logger


# ===========================================================================
# Section 2: GEO download and caching
# ===========================================================================

def fetch_geo_series(geo_id: str, cache_dir: Path, logger: logging.Logger):
    """
    Download a GEO series using GEOparse and cache to cache_dir.
    Returns a GEOparse GSE object.
    """
    try:
        import GEOparse  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "GEOparse is required: pip install GEOparse"
        ) from exc

    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Fetching {geo_id} (cache: {cache_dir})")
    gse = GEOparse.get_GEO(geo=geo_id, destdir=str(cache_dir), silent=True)
    logger.info(f"  {geo_id}: {len(gse.gsms)} samples loaded")
    return gse


# ===========================================================================
# Section 3: Metadata parsing
# ===========================================================================

def _first_matching_char(characteristics: dict, key_substring: str) -> str | None:
    """
    Return the VALUE of the first characteristic whose KEY contains key_substring
    (case-insensitive).  Trailing colons on key_substring are stripped before matching
    so that patterns like 'individual:' match unpacked keys like 'individual'.
    Returns None if no match.
    """
    needle = key_substring.rstrip(':').lower()
    for k, v in characteristics.items():
        if needle in k.lower():
            return str(v).strip() if v is not None else None
    return None


def _unpack_chars(metadata: dict) -> dict:
    """
    Convert GEOparse GSM metadata into a flat key→value dict suitable for
    _first_matching_char().  GEOparse stores all GSM characteristics as a
    list under the key 'characteristics_ch1' (and optionally 'characteristics_ch2'),
    where each element is a string like 'individual: 10, C' or 'brain region: hippocampus'.
    This helper unpacks those lists into the top-level dict so that
    _first_matching_char() can find fields like 'individual:' or 'brain region:'.
    """
    flat = {}
    for k, v in metadata.items():
        scalar = v[0] if isinstance(v, list) and len(v) > 0 else v
        flat[k] = scalar
        # Unpack GEO characteristics lists (characteristics_ch1, characteristics_ch2, …)
        if k.startswith('characteristics_ch') and isinstance(v, list):
            for item in v:
                if isinstance(item, str) and ':' in item:
                    ck, _, cv = item.partition(':')
                    flat[ck.strip()] = cv.strip()
    return flat


def parse_gse48350_metadata(gse, cfg: dict, logger: logging.Logger) -> pd.DataFrame:
    """
    Parse sample metadata for GSE48350 (GPL570).

    Characteristic layout (from series matrix / GEOparse):
      "individual: <id>, <DX>"  — DX is C (control) or AD
      "brain region: <region>"
      "gender: <M/F>"
      "age (yrs): <float>"

    Returns a DataFrame indexed by GSM ID with columns:
      gsm_id, diagnosis_code, diagnosis, age, sex_male, region
    """
    dx_pattern   = cfg["primary"]["diagnosis_field_pattern"]    # "individual:"
    cov_fields   = cfg["primary"]["covariate_fields"]
    keep_dx      = cfg["primary"]["keep_diagnoses"]             # [C, AD]
    dx_map       = cfg["primary"]["diagnosis_map"]              # {C:0, AD:1}

    records = []
    for gsm_id, gsm in gse.gsms.items():
        chars = gsm.metadata  # dict[str, list[str]]

        # Unpack characteristics_ch1 list into a searchable flat dict
        flat = _unpack_chars(chars)

        # --- diagnosis ---
        dx_raw = _first_matching_char(flat, dx_pattern)
        if dx_raw is None:
            logger.debug(f"GSE48350 {gsm_id}: missing diagnosis field, skipping")
            continue

        # Format: "GSE48350_<id>, <DX>"  or  "<id>, <DX>"
        # Extract the last comma-delimited token as the DX code
        dx_code = dx_raw.split(",")[-1].strip()
        if dx_code not in keep_dx:
            logger.debug(f"GSE48350 {gsm_id}: dx_code={dx_code!r} not in keep list, skipping")
            continue

        # --- covariates ---
        region_raw = _first_matching_char(flat, cov_fields["region"])
        sex_raw    = _first_matching_char(flat, cov_fields["sex"])
        age_raw    = _first_matching_char(flat, cov_fields["age"])

        try:
            age = float(age_raw) if age_raw is not None else float("nan")
        except ValueError:
            age = float("nan")

        # Normalise sex to binary (1=male, 0=female, NaN=unknown)
        if sex_raw is None:
            sex_male = float("nan")
        elif sex_raw.strip().upper() in ("M", "MALE"):
            sex_male = 1.0
        elif sex_raw.strip().upper() in ("F", "FEMALE"):
            sex_male = 0.0
        else:
            sex_male = float("nan")

        region = region_raw.strip().lower() if region_raw else None

        records.append({
            "gsm_id":        gsm_id,
            "diagnosis_code": dx_code,
            "diagnosis":     int(dx_map[dx_code]),
            "age":           age,
            "sex_male":      sex_male,
            "region":        region,
        })

    df = pd.DataFrame(records).set_index("gsm_id")
    logger.info(f"GSE48350 metadata: {len(df)} samples after diagnosis filter "
                f"(AD={df.diagnosis.sum()}, "
                f"C={(df.diagnosis == 0).sum()})")
    return df


def parse_gse122063_metadata(gse, cfg: dict, logger: logging.Logger) -> pd.DataFrame:
    """
    Parse sample metadata for GSE122063 (GPL16699).

    Characteristic layout:
      "patient diagnosis: <value>"
      "brain region: <value>"
      "Sex: <M/F>"
      "age: <float>"
      "pmi: <float>"
      "subject id: <id>"

    Steps applied:
      1. Keep only 'Alzheimer's disease' and 'Control'; exclude 'Vascular dementia'.
      2. Keep only frontal cortex samples.
      3. Collapse technical replicates (_TechRep1 / _TechRep2) to subject-level mean.

    Returns DataFrame indexed by a subject-region key with columns:
      subject_id, diagnosis_code, diagnosis, age, sex_male, pmi, region
    """
    dx_pattern     = cfg["replication"]["diagnosis_field_pattern"]
    cov_fields     = cfg["replication"]["covariate_fields"]
    keep_dx_vals   = cfg["replication"]["keep_diagnoses"]
    exclude_dx     = cfg["replication"]["exclude_diagnoses"]
    dx_map         = cfg["replication"]["diagnosis_map"]
    keep_region_sub = cfg["replication"]["keep_region_substring"].lower()  # "frontal"
    tech_rep_pat   = cfg["replication"]["tech_rep_pattern"]                # "_TechRep"

    records = []
    for gsm_id, gsm in gse.gsms.items():
        chars = gsm.metadata
        flat = _unpack_chars(chars)

        # --- diagnosis ---
        dx_raw = _first_matching_char(flat, dx_pattern)
        if dx_raw is None:
            continue
        dx_raw = dx_raw.strip()

        # Exclude vascular dementia
        if any(ex.lower() in dx_raw.lower() for ex in exclude_dx):
            logger.debug(f"GSE122063 {gsm_id}: excluded dx={dx_raw!r}")
            continue
        # Check exact keep list
        matched_dx = None
        for kd in keep_dx_vals:
            if kd.lower() in dx_raw.lower():
                matched_dx = kd
                break
        if matched_dx is None:
            logger.debug(f"GSE122063 {gsm_id}: dx={dx_raw!r} not in keep list, skipping")
            continue

        # --- region filter ---
        region_raw = _first_matching_char(flat, cov_fields["region"])
        if region_raw is None:
            continue
        region = region_raw.strip()
        if keep_region_sub not in region.lower():
            logger.debug(f"GSE122063 {gsm_id}: region={region!r} excluded")
            continue

        # --- other covariates ---
        sex_raw     = _first_matching_char(flat, cov_fields["sex"])
        age_raw     = _first_matching_char(flat, cov_fields["age"])
        pmi_raw     = _first_matching_char(flat, cov_fields["pmi"])
        subject_raw = _first_matching_char(flat, cov_fields["subject_id"])

        try:
            age = float(age_raw) if age_raw is not None else float("nan")
        except ValueError:
            age = float("nan")

        try:
            pmi = float(pmi_raw) if pmi_raw is not None else float("nan")
        except ValueError:
            pmi = float("nan")

        if sex_raw is None:
            sex_male = float("nan")
        elif sex_raw.strip().upper() in ("M", "MALE"):
            sex_male = 1.0
        elif sex_raw.strip().upper() in ("F", "FEMALE"):
            sex_male = 0.0
        else:
            sex_male = float("nan")

        # Detect technical-replicate label in GSM title
        title = gsm.metadata.get("title", [gsm_id])[0]
        is_tech_rep = tech_rep_pat.lower() in title.lower()
        # Normalise subject ID: strip TechRep suffix if present
        if subject_raw:
            subject_id = subject_raw.strip()
        else:
            # Fall back: strip TechRep suffix from title
            subject_id = title.split(tech_rep_pat)[0].strip() if is_tech_rep else title.strip()

        records.append({
            "gsm_id":         gsm_id,
            "subject_id":     subject_id,
            "diagnosis_code": matched_dx,
            "diagnosis":      int(dx_map[matched_dx]),
            "age":            age,
            "sex_male":       sex_male,
            "pmi":            pmi,
            "region":         region,
        })

    df_raw = pd.DataFrame(records)
    if df_raw.empty:
        logger.warning("GSE122063: no samples passed metadata filters!")
        return df_raw

    logger.info(f"GSE122063 metadata (pre-tech-rep collapse): {len(df_raw)} samples")

    # Collapse technical replicates: average numeric covariates per subject_id
    # (diagnosis, age, sex_male, pmi must be consistent within a subject)
    numeric_cols = ["age", "sex_male", "pmi"]
    agg_dict = {
        "diagnosis_code": "first",
        "diagnosis":      "first",
        "region":         "first",
    }
    for col in numeric_cols:
        agg_dict[col] = "mean"
    # We'll need to aggregate expression separately; here just metadata
    meta_collapsed = (
        df_raw.groupby("subject_id", as_index=False)
        .agg(agg_dict)
    )
    meta_collapsed.set_index("subject_id", inplace=True)

    logger.info(f"GSE122063 metadata (post-tech-rep collapse): {len(meta_collapsed)} subjects "
                f"(AD={meta_collapsed.diagnosis.sum()}, "
                f"C={(meta_collapsed.diagnosis == 0).sum()})")
    return meta_collapsed


# ===========================================================================
# Section 4: Expression matrix extraction and probe→gene collapse
# ===========================================================================

def extract_expression_matrix(gse, logger: logging.Logger) -> pd.DataFrame:
    """
    Extract the raw expression table from a GEOparse GSE object.
    Returns a DataFrame: rows = probe IDs, columns = GSM IDs.
    """
    logger.info("Extracting expression matrix from pivot table...")
    try:
        expr = gse.pivot_samples("VALUE")
    except Exception as exc:
        logger.warning(f"pivot_samples('VALUE') failed ({exc}); trying 'value'")
        try:
            expr = gse.pivot_samples("value")
        except Exception as exc2:
            raise RuntimeError(
                f"Cannot extract expression matrix: {exc2}"
            ) from exc2

    logger.info(f"  Expression matrix shape: {expr.shape} (probes × samples)")
    # Coerce to float
    expr = expr.apply(pd.to_numeric, errors="coerce")
    return expr


def build_probe_gene_map(gse, platform_id: str, logger: logging.Logger) -> pd.Series:
    """
    Return a Series mapping probe_id → gene_symbol for the given platform.
    Uses the GPL annotation from the GSE object.

    Priority order for gene-symbol column:
      'Gene Symbol', 'GENE_SYMBOL', 'gene_assignment', 'GB_ACC'
    """
    try:
        gpl = gse.gpls[platform_id]
    except KeyError:
        available = list(gse.gpls.keys())
        logger.warning(f"Platform {platform_id} not found; available: {available}. "
                       "Trying first available platform.")
        gpl = list(gse.gpls.values())[0]

    ann = gpl.table
    logger.info(f"GPL annotation columns: {list(ann.columns)}")

    # Attempt to find a gene symbol column
    symbol_col = None
    for candidate in ["Gene Symbol", "GENE_SYMBOL", "gene_assignment",
                       "ILMN_Gene", "ORF", "GB_ACC"]:
        if candidate in ann.columns:
            symbol_col = candidate
            logger.info(f"  Using gene-symbol column: {symbol_col!r}")
            break

    if symbol_col is None:
        raise RuntimeError(
            f"No recognisable gene-symbol column in GPL table. "
            f"Available: {list(ann.columns)}"
        )

    # Probe ID is typically the index or 'ID' column
    if "ID" in ann.columns:
        probe_gene = ann.set_index("ID")[symbol_col]
    else:
        probe_gene = ann[symbol_col]

    # For platforms like Agilent 'gene_assignment', extract the first token
    # (format: "NM_xxx // GENE_SYMBOL // ...") — keep only the gene symbol part
    if symbol_col in ("gene_assignment",):
        def _extract_symbol(val):
            if pd.isna(val) or str(val).strip() in ("", "---"):
                return None
            parts = str(val).split("//")
            if len(parts) >= 2:
                return parts[1].strip()
            return parts[0].strip()
        probe_gene = probe_gene.apply(_extract_symbol)
    else:
        # Strip whitespace; replace '---' / '' with None
        probe_gene = probe_gene.apply(
            lambda x: x.strip() if isinstance(x, str) and x.strip() not in ("", "---") else None
        )
        # Some platforms list multiple symbols separated by ' /// '
        probe_gene = probe_gene.apply(
            lambda x: x.split(" /// ")[0].strip() if isinstance(x, str) else x
        )

    probe_gene.name = "gene_symbol"
    n_mapped = probe_gene.notna().sum()
    logger.info(f"  Probe→gene map: {len(probe_gene)} probes, {n_mapped} with gene symbol")
    return probe_gene


def collapse_probes_to_genes(
    expr: pd.DataFrame,
    probe_gene: pd.Series,
    panel_genes: list[str],
    method: str,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Collapse probe-level expression to gene-level for the analysis panel.

    For each panel gene:
      - Find all probes mapped to that gene.
      - If method == 'max_variance': select the probe with the highest variance
        across samples (within this expression matrix).
      - Fallback (if only one probe or variances are tied): use that probe.
      - Documented fallback: 'mean' — average across all probes for the gene.

    Returns DataFrame: rows = panel genes present on platform, columns = sample IDs.
    Logs genes missing from the platform.
    """
    # Align probe_gene index to expression matrix index
    common_probes = expr.index.intersection(probe_gene.index)
    if len(common_probes) < len(expr.index):
        logger.debug(f"  {len(expr.index) - len(common_probes)} probes have no annotation match")
    probe_gene_filtered = probe_gene.loc[common_probes]

    gene_expr_rows = {}
    missing_genes  = []

    for gene in panel_genes:
        gene_upper = gene.upper()
        # Case-insensitive match
        probe_ids = probe_gene_filtered[
            probe_gene_filtered.str.upper() == gene_upper
        ].index.tolist() if probe_gene_filtered.notna().any() else []

        if len(probe_ids) == 0:
            missing_genes.append(gene)
            logger.info(f"  Panel gene {gene}: NOT FOUND on platform — will be flagged untestable")
            continue

        probe_expr = expr.loc[probe_ids]  # shape: (n_probes, n_samples)
        if probe_expr.shape[0] == 1 or method == "mean":
            gene_expr_rows[gene] = probe_expr.mean(axis=0)
        else:
            # max-variance probe
            variances = probe_expr.var(axis=1)
            best_probe = variances.idxmax()
            gene_expr_rows[gene] = probe_expr.loc[best_probe]
            logger.debug(f"  {gene}: {len(probe_ids)} probes → selected {best_probe} "
                         f"(var={variances[best_probe]:.4f})")

    if not gene_expr_rows:
        logger.warning("No panel genes found on this platform!")
        return pd.DataFrame(columns=expr.columns)

    result = pd.DataFrame(gene_expr_rows).T   # (genes, samples)
    result.columns = expr.columns
    logger.info(f"  Collapsed to {len(result)} panel genes ({len(missing_genes)} missing)")
    return result, missing_genes


# ===========================================================================
# Section 5: OLS modeling
# ===========================================================================

def _safe_ols_gene(
    gene: str,
    expr_row: pd.Series,
    meta: pd.DataFrame,
    formula_rhs: str,
    logger: logging.Logger,
) -> dict:
    """
    Fit OLS for one gene. Resilient: on any failure returns NaN values and logs
    the failure reason.  Never raises.

    Returns a dict with:
      gene, n_obs, coef_diagnosis, se, t_stat, p_value, ci_low, ci_high,
      std_beta (standardised coefficient), error (None or str)
    """
    import statsmodels.formula.api as smf

    base_result = {
        "gene":            gene,
        "n_obs":           np.nan,
        "coef_diagnosis":  np.nan,
        "se":              np.nan,
        "t_stat":          np.nan,
        "p_value":         np.nan,
        "ci_low":          np.nan,
        "ci_high":         np.nan,
        "std_beta":        np.nan,
        "error":           None,
    }

    try:
        # Align meta and expression
        common_idx = meta.index.intersection(expr_row.index)
        if len(common_idx) < 5:
            base_result["error"] = f"too_few_samples (n={len(common_idx)})"
            return base_result

        df_model = meta.loc[common_idx].copy()
        df_model["expression"] = expr_row.loc[common_idx].values

        # Drop rows with any NaN in required columns
        required_cols = ["expression", "diagnosis"] + [
            c for c in ["age", "sex_male", "region", "pmi"] if c in df_model.columns
        ]
        df_model = df_model[required_cols].dropna()

        if len(df_model) < 5:
            base_result["error"] = f"too_few_complete_cases (n={len(df_model)})"
            return base_result

        # Ensure diagnosis has variation
        if df_model["diagnosis"].nunique() < 2:
            base_result["error"] = "no_diagnosis_variation"
            return base_result

        formula = f"expression ~ {formula_rhs}"
        model   = smf.ols(formula, data=df_model).fit()

        # Find the diagnosis coefficient (binary: coefficient for diagnosis==1)
        # statsmodels names it 'diagnosis' or 'diagnosis[T.1]' depending on dtype
        coef_name = None
        for cand in ["diagnosis", "diagnosis[T.1]", "C(diagnosis)[T.1]"]:
            if cand in model.params.index:
                coef_name = cand
                break
        if coef_name is None:
            # Try partial match
            matches = [p for p in model.params.index if "diagnosis" in p.lower()]
            if matches:
                coef_name = matches[0]
        if coef_name is None:
            base_result["error"] = "diagnosis_coef_not_found"
            return base_result

        coef    = model.params[coef_name]
        se      = model.bse[coef_name]
        t_stat  = model.tvalues[coef_name]
        p_val   = model.pvalues[coef_name]
        ci      = model.conf_int().loc[coef_name]

        # Standardised beta: coef * SD(diagnosis) / SD(expression)
        sd_dx   = df_model["diagnosis"].std()
        sd_expr = df_model["expression"].std()
        std_beta = (coef * sd_dx / sd_expr) if sd_expr > 0 else np.nan

        base_result.update({
            "n_obs":           len(df_model),
            "coef_diagnosis":  coef,
            "se":              se,
            "t_stat":          t_stat,
            "p_value":         p_val,
            "ci_low":          float(ci.iloc[0]),
            "ci_high":         float(ci.iloc[1]),
            "std_beta":        std_beta,
        })

    except Exception as exc:
        base_result["error"] = str(exc)[:120]
        logger.warning(f"  OLS failed for gene {gene}: {exc}")

    return base_result


def run_ols_panel(
    gene_expr: pd.DataFrame,   # rows=genes, columns=sample_ids
    meta: pd.DataFrame,
    formula_rhs: str,
    label: str,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Fit OLS for every gene in gene_expr.  Returns results DataFrame.
    """
    logger.info(f"Fitting OLS [{label}]: {len(gene_expr)} genes, formula RHS: {formula_rhs}")
    results = []
    for gene in gene_expr.index:
        expr_row = gene_expr.loc[gene]
        res = _safe_ols_gene(gene, expr_row, meta, formula_rhs, logger)
        results.append(res)
    df_res = pd.DataFrame(results).set_index("gene")
    n_failed = df_res["error"].notna().sum()
    if n_failed:
        logger.warning(f"  [{label}] {n_failed} gene(s) failed OLS — see 'error' column")
    logger.info(f"  [{label}] OLS complete: {len(df_res)} genes")
    return df_res


# ===========================================================================
# Section 6: Multiple-testing correction
# ===========================================================================

def apply_multiple_testing(p_values: pd.Series, alpha: float, logger: logging.Logger) -> pd.DataFrame:
    """
    Apply Bonferroni and Benjamini-Hochberg FDR corrections to p_values.
    Returns DataFrame with columns: p_value, p_bonferroni, p_bh, reject_bonferroni, reject_bh.
    """
    from statsmodels.stats.multitest import multipletests

    valid_mask = p_values.notna()
    n_tests    = valid_mask.sum()
    logger.info(f"  Multiple testing: {n_tests} valid p-values over {len(p_values)} panel genes")

    result = pd.DataFrame(index=p_values.index)
    result["p_value"]          = p_values
    result["p_bonferroni"]     = np.nan
    result["p_bh"]             = np.nan
    result["reject_bonferroni"] = False
    result["reject_bh"]        = False

    if n_tests == 0:
        logger.warning("No valid p-values to correct.")
        return result

    pvals_valid = p_values[valid_mask].values

    # Bonferroni
    rej_bonf, p_bonf, _, _ = multipletests(pvals_valid, alpha=alpha, method="bonferroni")
    # Benjamini-Hochberg
    rej_bh, p_bh, _, _     = multipletests(pvals_valid, alpha=alpha, method="fdr_bh")

    result.loc[valid_mask, "p_bonferroni"]     = p_bonf
    result.loc[valid_mask, "p_bh"]             = p_bh
    result.loc[valid_mask, "reject_bonferroni"] = rej_bonf
    result.loc[valid_mask, "reject_bh"]         = rej_bh

    n_bonf = rej_bonf.sum()
    n_bh   = rej_bh.sum()
    logger.info(f"  Bonferroni significant: {n_bonf}  |  BH-FDR significant: {n_bh}")
    return result


# ===========================================================================
# Section 7: Bootstrap CIs on standardised effect size
# ===========================================================================

def bootstrap_effect_size_ci(
    gene: str,
    expr_row: pd.Series,
    meta: pd.DataFrame,
    formula_rhs: str,
    n_iter: int,
    ci_level: float,
    seed: int,
    logger: logging.Logger,
) -> dict:
    """
    Bootstrap CI on std_beta for one gene.  Returns dict with
    boot_ci_low, boot_ci_high, boot_median.
    """
    rng = np.random.default_rng(seed)
    common_idx = meta.index.intersection(expr_row.index)
    df_model = meta.loc[common_idx].copy()
    df_model["expression"] = expr_row.loc[common_idx].values

    required_cols = ["expression", "diagnosis"] + [
        c for c in ["age", "sex_male", "region", "pmi"] if c in df_model.columns
    ]
    df_model = df_model[required_cols].dropna()

    if len(df_model) < 5 or df_model["diagnosis"].nunique() < 2:
        return {"boot_ci_low": np.nan, "boot_ci_high": np.nan, "boot_median": np.nan}

    import statsmodels.formula.api as smf

    boot_betas = []
    formula    = f"expression ~ {formula_rhs}"

    for _ in range(n_iter):
        sample = df_model.sample(n=len(df_model), replace=True, random_state=int(rng.integers(1e9)))
        # Skip bootstrap resamples with no diagnosis variation
        if sample["diagnosis"].nunique() < 2:
            continue
        try:
            m = smf.ols(formula, data=sample).fit()
            coef_name = None
            for cand in ["diagnosis", "diagnosis[T.1]", "C(diagnosis)[T.1]"]:
                if cand in m.params.index:
                    coef_name = cand
                    break
            if coef_name is None:
                matches = [p for p in m.params.index if "diagnosis" in p.lower()]
                if matches:
                    coef_name = matches[0]
            if coef_name is None:
                continue
            coef    = m.params[coef_name]
            sd_dx   = sample["diagnosis"].std()
            sd_expr = sample["expression"].std()
            if sd_expr > 0:
                boot_betas.append(coef * sd_dx / sd_expr)
        except Exception:
            continue

    if len(boot_betas) < 10:
        return {"boot_ci_low": np.nan, "boot_ci_high": np.nan, "boot_median": np.nan}

    alpha_tail = (1.0 - ci_level) / 2.0
    lower = np.percentile(boot_betas, 100.0 * alpha_tail)
    upper = np.percentile(boot_betas, 100.0 * (1.0 - alpha_tail))
    median = np.median(boot_betas)
    return {"boot_ci_low": lower, "boot_ci_high": upper, "boot_median": median}


def run_bootstrap_panel(
    gene_expr: pd.DataFrame,
    meta: pd.DataFrame,
    formula_rhs: str,
    n_iter: int,
    ci_level: float,
    seed: int,
    logger: logging.Logger,
) -> pd.DataFrame:
    logger.info(f"Bootstrapping effect-size CIs: {len(gene_expr)} genes, "
                f"n_iter={n_iter}, ci={ci_level}")
    results = {}
    for gene in gene_expr.index:
        results[gene] = bootstrap_effect_size_ci(
            gene, gene_expr.loc[gene], meta, formula_rhs, n_iter, ci_level, seed, logger
        )
    return pd.DataFrame(results).T


# ===========================================================================
# Section 8: Power assessment
# ===========================================================================

def power_assessment(
    n_per_group: int,
    effect_sizes: list[float],
    alpha: float,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Compute two-sample t-test power for given effect sizes and n_per_group.
    Uses statsmodels TTestIndPower.
    """
    from statsmodels.stats.power import TTestIndPower

    analysis = TTestIndPower()
    rows = []
    for d in effect_sizes:
        pwr = analysis.power(effect_size=d, nobs1=n_per_group, alpha=alpha, ratio=1.0)
        rows.append({"effect_size_d": d, "n_per_group": n_per_group,
                     "alpha": alpha, "power": pwr})
        logger.info(f"  Power |d|={d}: n_per_group={n_per_group} → power={pwr:.3f}")
    return pd.DataFrame(rows)


# ===========================================================================
# Section 9: Per-region robustness check
# ===========================================================================

def run_per_region_robustness(
    gene_expr_primary: pd.DataFrame,
    meta_primary: pd.DataFrame,
    regions: list[str],
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Fit OLS separately for each brain region in GSE48350.
    Formula within a region: expression ~ diagnosis + age + sex_male
    (no region covariate since only one region is in the subset).
    Returns a long-form DataFrame: region, gene, coef_diagnosis, p_value, n_obs, error.
    """
    logger.info("Robustness check 1: per-region OLS in GSE48350")
    all_rows = []
    for region in regions:
        region_mask = meta_primary["region"].str.lower() == region.lower()
        region_meta = meta_primary[region_mask]
        n_region    = region_mask.sum()
        logger.info(f"  Region: {region!r}, n={n_region}")

        if n_region < 5:
            logger.warning(f"  Skipping {region!r}: too few samples ({n_region})")
            continue

        # Subset expression matrix to samples in this region
        region_gsms = region_meta.index
        common_gsms = gene_expr_primary.columns.intersection(region_gsms)
        expr_region = gene_expr_primary[common_gsms]

        # Formula: no region term since we're within a single region
        formula_rhs = "diagnosis + age + sex_male"
        res = run_ols_panel(expr_region, region_meta, formula_rhs,
                            label=f"GSE48350 [{region}]", logger=logger)
        res["region"] = region
        all_rows.append(res.reset_index())

    if not all_rows:
        return pd.DataFrame()
    df_rob = pd.concat(all_rows, ignore_index=True)
    df_rob = df_rob[["region", "gene", "coef_diagnosis", "p_value", "n_obs", "error"]]
    return df_rob


# ===========================================================================
# Section 10: Direction replication check
# ===========================================================================

def check_direction_replication(
    primary_results: pd.DataFrame,
    replication_results: pd.DataFrame,
    sig_genes: list[str],
    rep_alpha: float,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    For genes significant (BH-FDR < 0.05) in the primary analysis, check:
      - Same sign of diagnosis coefficient in GSE122063 frontal cortex.
      - Nominal p < rep_alpha in GSE122063.

    Returns a DataFrame recording replication status per gene.
    """
    rows = []
    for gene in sig_genes:
        if gene not in primary_results.index or gene not in replication_results.index:
            rows.append({"gene": gene, "replicated": False,
                         "replication_reason": "gene_missing_in_replication_dataset"})
            continue

        prim_coef = primary_results.loc[gene, "coef_diagnosis"]
        rep_coef  = replication_results.loc[gene, "coef_diagnosis"]
        rep_pval  = replication_results.loc[gene, "p_value"]

        same_sign = (np.sign(prim_coef) == np.sign(rep_coef)) if (
            np.isfinite(prim_coef) and np.isfinite(rep_coef)) else False
        rep_sig   = (np.isfinite(rep_pval) and rep_pval < rep_alpha)
        replicated = same_sign and rep_sig

        rows.append({
            "gene":              gene,
            "primary_coef":      prim_coef,
            "replication_coef":  rep_coef,
            "replication_pval":  rep_pval,
            "same_sign":         same_sign,
            "rep_nominal_sig":   rep_sig,
            "replicated":        replicated,
            "replication_reason": (
                "REPLICATED" if replicated
                else ("wrong_sign" if not same_sign else "not_nominally_sig")
            ),
        })
        logger.info(f"  {gene}: primary_coef={prim_coef:.4f}, rep_coef={rep_coef:.4f}, "
                    f"rep_p={rep_pval:.4f} → {'REPLICATED' if replicated else 'NOT replicated'}")

    return pd.DataFrame(rows)


# ===========================================================================
# Section 11: Figures
# ===========================================================================

def make_forest_plot(
    primary_ols: pd.DataFrame,
    replication_ols: pd.DataFrame,
    mt_results: pd.DataFrame,
    panel_genes: list[str],
    figures_dir: Path,
    logger: logging.Logger,
) -> None:
    """
    Forest plot: one row per panel gene, two markers per row
    (GSE48350 blue circle, GSE122063 orange diamond).
    X-axis = diagnosis coefficient (OLS).
    Bars = 95 % CI from model (primary) or model (replication).
    Stars mark BH-FDR < 0.05 genes.

    Saved as .png and .pdf.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    figures_dir.mkdir(parents=True, exist_ok=True)

    # Restrict to genes present in at least one result set
    genes_to_plot = [g for g in panel_genes
                     if g in primary_ols.index or g in replication_ols.index]
    if not genes_to_plot:
        logger.warning("Forest plot: no genes to plot")
        return

    n = len(genes_to_plot)
    fig_height = max(5, n * 0.5)
    fig, ax = plt.subplots(figsize=(9, fig_height))

    y_positions = np.arange(n)
    offset      = 0.18  # vertical offset between primary and replication markers

    for i, gene in enumerate(genes_to_plot):
        y_base = y_positions[i]

        # --- Primary (GSE48350) ---
        if gene in primary_ols.index:
            coef = primary_ols.loc[gene, "coef_diagnosis"]
            ci_l = primary_ols.loc[gene, "ci_low"]
            ci_h = primary_ols.loc[gene, "ci_high"]
            if np.isfinite(coef):
                ax.errorbar(
                    coef, y_base + offset,
                    xerr=[[coef - ci_l], [ci_h - coef]] if np.isfinite(ci_l) else None,
                    fmt="o", color="#2166ac", markersize=6,
                    elinewidth=1.2, capsize=3, label="GSE48350" if i == 0 else "",
                )

        # --- Replication (GSE122063) ---
        if gene in replication_ols.index:
            coef_r = replication_ols.loc[gene, "coef_diagnosis"]
            ci_l_r = replication_ols.loc[gene, "ci_low"]
            ci_h_r = replication_ols.loc[gene, "ci_high"]
            if np.isfinite(coef_r):
                ax.errorbar(
                    coef_r, y_base - offset,
                    xerr=[[coef_r - ci_l_r], [ci_h_r - coef_r]] if np.isfinite(ci_l_r) else None,
                    fmt="D", color="#d6604d", markersize=5,
                    elinewidth=1.2, capsize=3, label="GSE122063 frontal" if i == 0 else "",
                )

        # BH-FDR star annotation
        if gene in mt_results.index and mt_results.loc[gene, "reject_bh"]:
            ax.text(
                ax.get_xlim()[1] if ax.get_xlim()[1] != 0 else 0.5,
                y_base, "*", ha="left", va="center",
                fontsize=12, color="black",
            )

    ax.axvline(0, color="grey", linestyle="--", linewidth=0.8, zorder=0)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(genes_to_plot, fontsize=9)
    ax.set_xlabel("Diagnosis coefficient (AD vs control)", fontsize=10)
    ax.set_title(
        "H002: T2D–AD panel gene differential expression\n"
        "Forest plot (OLS coef ± 95 % CI); * = BH-FDR < 0.05 in GSE48350",
        fontsize=10,
    )

    blue_patch  = mpatches.Patch(color="#2166ac", label="GSE48350 (primary)")
    red_patch   = mpatches.Patch(color="#d6604d", label="GSE122063 frontal (replication)")
    ax.legend(handles=[blue_patch, red_patch], fontsize=8, loc="lower right")
    ax.invert_yaxis()
    fig.tight_layout()

    for ext in ("png", "pdf"):
        fpath = figures_dir / f"H002_forest_plot.{ext}"
        fig.savefig(fpath, dpi=150 if ext == "png" else None, bbox_inches="tight")
        logger.info(f"  Saved figure: {fpath}")

    plt.close(fig)


# ===========================================================================
# Section 12: Collapse tech-rep expression for GSE122063
# ===========================================================================

def collapse_tech_rep_expression(
    expr: pd.DataFrame,
    raw_meta: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Given probe-level expression (columns = gsm_ids) and raw metadata
    (index = gsm_ids, with 'subject_id' column), average expression
    across technical replicates, producing one column per subject_id.
    """
    gsm_to_subject = raw_meta["subject_id"] if "subject_id" in raw_meta.columns else None
    if gsm_to_subject is None:
        logger.warning("No subject_id column for tech-rep collapse; returning as-is")
        return expr

    common_gsms = expr.columns.intersection(gsm_to_subject.index)
    if len(common_gsms) < len(expr.columns):
        logger.debug(f"Tech-rep collapse: {len(expr.columns) - len(common_gsms)} "
                     "expression columns not in metadata; dropping")

    expr_sub = expr[common_gsms]
    subject_map = gsm_to_subject.loc[common_gsms]

    # Group columns by subject_id and average
    collapsed = {}
    for subj_id, gsm_ids in subject_map.groupby(subject_map).groups.items():
        collapsed[subj_id] = expr_sub[gsm_ids].mean(axis=1)

    result = pd.DataFrame(collapsed)  # rows=probes, columns=subject_ids
    logger.info(f"  Tech-rep collapse: {expr_sub.shape[1]} GSMs → "
                f"{result.shape[1]} subjects (probes preserved: {result.shape[0]})")
    return result


# ===========================================================================
# Main entry point
# ===========================================================================

def main():
    # ------------------------------------------------------------------
    # 0. Paths
    # ------------------------------------------------------------------
    config_path  = PROJECT_ROOT / "experiments" / "H002" / "config.yaml"
    cfg          = load_config(config_path)

    log_file     = PROJECT_ROOT / cfg["log_file"]
    results_dir  = PROJECT_ROOT / cfg["results_dir"]
    figures_dir  = PROJECT_ROOT / cfg["figures_dir"]
    geo_cache    = PROJECT_ROOT / cfg["geo_cache_dir"]

    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Logger
    # ------------------------------------------------------------------
    logger = setup_logger(log_file)

    # ------------------------------------------------------------------
    # 2. Reproducibility metadata
    # ------------------------------------------------------------------
    seed = cfg["random_seed"]
    np.random.seed(seed)

    start_ts = log_run_metadata(logger, seeds=[seed], phase="start")
    logger.info(f"Experiment: {cfg['experiment_id']}")
    logger.info(f"Config:     {config_path}")
    logger.info(f"Hypothesis: {PROJECT_ROOT / cfg['provenance']['hypothesis_file']}")

    panel_genes   = cfg["panel_genes"]
    central_genes = cfg["central_genes"]
    logger.info(f"Panel genes ({len(panel_genes)}): {panel_genes}")
    logger.info(f"Central genes: {central_genes}")

    # ===================================================================
    # PRIMARY DATASET: GSE48350
    # ===================================================================
    logger.info("=" * 60)
    logger.info("PRIMARY: GSE48350 (GPL570, Affymetrix)")
    logger.info("=" * 60)

    gse_primary = fetch_geo_series(cfg["primary"]["geo_id"], geo_cache, logger)

    # --- Metadata ---
    meta_primary_raw = parse_gse48350_metadata(gse_primary, cfg, logger)

    # --- Expression matrix ---
    expr_primary_raw = extract_expression_matrix(gse_primary, logger)

    # --- Probe→gene map ---
    probe_gene_primary = build_probe_gene_map(
        gse_primary, cfg["primary"]["platform"], logger
    )

    # --- Probe→gene collapse for panel ---
    result_collapse_primary = collapse_probes_to_genes(
        expr_primary_raw, probe_gene_primary, panel_genes,
        cfg["primary"]["probe_collapse_method"], logger
    )
    # collapse_probes_to_genes returns (df, missing_genes)
    if isinstance(result_collapse_primary, tuple):
        gene_expr_primary, missing_primary = result_collapse_primary
    else:
        gene_expr_primary, missing_primary = result_collapse_primary, []

    logger.info(f"GSE48350: {len(gene_expr_primary)} panel genes available; "
                f"{len(missing_primary)} untestable: {missing_primary}")

    # --- Align samples: keep only samples in metadata ---
    common_primary = gene_expr_primary.columns.intersection(meta_primary_raw.index)
    gene_expr_primary = gene_expr_primary[common_primary]
    meta_primary      = meta_primary_raw.loc[common_primary]

    # --- Primary OLS (all regions) ---
    # Formula: expression ~ diagnosis + age + sex_male + C(region)
    # Use treatment-coding for region (statsmodels handles C(region))
    primary_formula_rhs = "diagnosis + age + sex_male + C(region)"
    primary_ols = run_ols_panel(
        gene_expr_primary, meta_primary, primary_formula_rhs,
        label="GSE48350 all-regions", logger=logger
    )

    # --- Multiple testing correction ---
    mt_results = apply_multiple_testing(
        primary_ols["p_value"], cfg["modeling"]["alpha"], logger
    )
    primary_ols = primary_ols.join(mt_results[["p_bonferroni", "p_bh",
                                                "reject_bonferroni", "reject_bh"]])

    sig_bh_genes = list(primary_ols[primary_ols["reject_bh"]].index)
    logger.info(f"BH-FDR significant genes in GSE48350: {sig_bh_genes}")

    # --- Bootstrap CIs ---
    boot_cfg = cfg["modeling"]
    boot_df  = run_bootstrap_panel(
        gene_expr_primary, meta_primary, primary_formula_rhs,
        n_iter=boot_cfg["bootstrap_n_iterations"],
        ci_level=boot_cfg["bootstrap_ci_level"],
        seed=seed, logger=logger
    )
    primary_ols = primary_ols.join(boot_df, how="left")

    # --- Power assessment ---
    # Use median per-region n (AD + control combined) as a conservative estimate
    region_counts = meta_primary.groupby("region")["diagnosis"].value_counts()
    per_region_ns = meta_primary.groupby("region").size()
    min_group_n   = int(per_region_ns.min() // 2)  # rough: assume balanced
    min_group_n   = max(min_group_n, 5)             # floor for degenerate cases

    power_df = power_assessment(
        n_per_group=min_group_n,
        effect_sizes=cfg["power"]["effect_sizes_to_check"],
        alpha=cfg["power"]["alpha_power"],
        logger=logger,
    )
    logger.info(f"Power note: using n_per_group={min_group_n} (min per-region, half-split approx)")

    # --- Robustness check 1: per-region ---
    robustness_df = run_per_region_robustness(
        gene_expr_primary, meta_primary,
        regions=cfg["primary"]["keep_regions"],
        logger=logger
    )

    # ===================================================================
    # REPLICATION DATASET: GSE122063 (frontal cortex only)
    # ===================================================================
    logger.info("=" * 60)
    logger.info("REPLICATION: GSE122063 (GPL16699, Agilent, frontal cortex)")
    logger.info("=" * 60)

    gse_rep = fetch_geo_series(cfg["replication"]["geo_id"], geo_cache, logger)

    # --- Metadata (with tech-rep collapse) ---
    # parse_gse122063_metadata returns subject-level metadata (post-collapse)
    # We also need a gsm→subject mapping to collapse expression
    # Build raw pre-collapse metadata first for expression alignment
    meta_rep_raw_pre_collapse = []
    for gsm_id, gsm in gse_rep.gsms.items():
        chars = gsm.metadata
        flat = _unpack_chars(chars)
        dx_raw = _first_matching_char(flat, cfg["replication"]["diagnosis_field_pattern"])
        if dx_raw is None:
            continue
        dx_raw = dx_raw.strip()
        if any(ex.lower() in dx_raw.lower() for ex in cfg["replication"]["exclude_diagnoses"]):
            continue
        region_raw = _first_matching_char(flat, cfg["replication"]["covariate_fields"]["region"])
        if region_raw is None:
            continue
        if cfg["replication"]["keep_region_substring"].lower() not in region_raw.lower():
            continue
        subject_raw = _first_matching_char(flat, cfg["replication"]["covariate_fields"]["subject_id"])
        title = gsm.metadata.get("title", [gsm_id])[0]
        tech_pat = cfg["replication"]["tech_rep_pattern"]
        if subject_raw:
            subject_id = subject_raw.strip()
        else:
            subject_id = title.split(tech_pat)[0].strip() if tech_pat.lower() in title.lower() else title.strip()
        meta_rep_raw_pre_collapse.append({"gsm_id": gsm_id, "subject_id": subject_id})

    gsm_subject_df = pd.DataFrame(meta_rep_raw_pre_collapse).set_index("gsm_id")

    # --- Expression matrix ---
    expr_rep_raw = extract_expression_matrix(gse_rep, logger)

    # --- Collapse technical replicates in expression ---
    expr_rep_collapsed = collapse_tech_rep_expression(expr_rep_raw, gsm_subject_df, logger)

    # --- Probe→gene map ---
    probe_gene_rep = build_probe_gene_map(
        gse_rep, cfg["replication"]["platform"], logger
    )

    # --- Probe→gene collapse for panel ---
    result_collapse_rep = collapse_probes_to_genes(
        expr_rep_collapsed, probe_gene_rep, panel_genes,
        cfg["replication"]["probe_collapse_method"], logger
    )
    if isinstance(result_collapse_rep, tuple):
        gene_expr_rep, missing_rep = result_collapse_rep
    else:
        gene_expr_rep, missing_rep = result_collapse_rep, []

    logger.info(f"GSE122063: {len(gene_expr_rep)} panel genes available; "
                f"{len(missing_rep)} untestable: {missing_rep}")

    # --- Subject-level metadata (post-collapse) ---
    meta_rep = parse_gse122063_metadata(gse_rep, cfg, logger)

    # --- Align samples ---
    common_rep = gene_expr_rep.columns.intersection(meta_rep.index)
    gene_expr_rep = gene_expr_rep[common_rep]
    meta_rep      = meta_rep.loc[common_rep]

    # --- Replication OLS (frontal cortex; no region covariate) ---
    # TODO: If PMI is missing for many subjects, consider whether to drop pmi from formula.
    rep_formula_rhs = "diagnosis + age + sex_male"
    if meta_rep["pmi"].notna().mean() >= 0.5:
        rep_formula_rhs = "diagnosis + age + sex_male + pmi"
        logger.info("PMI available in ≥50% of replication samples; including pmi in formula")
    else:
        logger.info("PMI missing in >50% of replication samples; EXCLUDING pmi from formula")

    rep_ols = run_ols_panel(
        gene_expr_rep, meta_rep, rep_formula_rhs,
        label="GSE122063 frontal", logger=logger
    )

    # ===================================================================
    # Direction replication check
    # ===================================================================
    logger.info("=" * 60)
    logger.info("Cross-platform direction replication")
    logger.info("=" * 60)

    replication_status = check_direction_replication(
        primary_ols, rep_ols, sig_bh_genes,
        rep_alpha=cfg["modeling"]["replication_nominal_alpha"],
        logger=logger,
    )

    # ===================================================================
    # Flags and caveats
    # ===================================================================
    all_missing = list(set(missing_primary + missing_rep))
    untestable_genes = list(set(missing_primary) | set(missing_rep))

    if "APOE" in panel_genes:
        logger.warning(
            "APOE CAVEAT: Microarray probes quantify APOE mRNA ONLY. "
            "APOE ε2/ε3/ε4 allele status is NOT available. "
            "Any APOE signal is transcript-level and MUST NOT be interpreted "
            "as an ε4 dosage or genotype effect."
        )
    logger.info(
        "MULTIPLE-TESTING NOTE: Corrections (Bonferroni + BH-FDR) are applied over "
        f"the {len(panel_genes)}-gene panel ONLY (confirmatory, pre-registered). "
        "Results do NOT licence genome-wide or causal claims."
    )

    # ===================================================================
    # Figures (Robustness check 3 is bootstrap CIs, already computed)
    # ===================================================================
    logger.info("Building forest plot...")
    make_forest_plot(
        primary_ols, rep_ols, mt_results, panel_genes, figures_dir, logger
    )

    # ===================================================================
    # Save metrics.csv
    # ===================================================================
    logger.info("Saving results/metrics.csv ...")
    metrics_path = results_dir / "metrics.csv"

    # Primary OLS with MT corrections + bootstrap CIs
    primary_out = primary_ols.copy().reset_index()
    primary_out.insert(0, "dataset",        "GSE48350")
    primary_out.insert(1, "analysis_scope", "all_regions")
    primary_out.insert(2, "run_timestamp",  start_ts)
    primary_out.insert(3, "random_seed",    seed)
    primary_out.insert(4, "n_panel_genes",  len(panel_genes))
    primary_out.insert(5, "n_untestable",   len(untestable_genes))
    primary_out.insert(6, "untestable",     str(untestable_genes))

    # Replication OLS
    rep_out = rep_ols.copy().reset_index()
    rep_out.insert(0, "dataset",        "GSE122063")
    rep_out.insert(1, "analysis_scope", "frontal_cortex")
    rep_out.insert(2, "run_timestamp",  start_ts)
    rep_out.insert(3, "random_seed",    seed)

    # Combine
    combined = pd.concat([primary_out, rep_out], ignore_index=True, sort=False)
    combined.to_csv(metrics_path, index=False)
    logger.info(f"  metrics.csv saved: {metrics_path} ({len(combined)} rows)")

    # Per-region robustness
    if not robustness_df.empty:
        rob_path = results_dir / "metrics_per_region.csv"
        robustness_df.to_csv(rob_path, index=False)
        logger.info(f"  Per-region metrics saved: {rob_path}")

    # Replication status
    if not replication_status.empty:
        rep_status_path = results_dir / "metrics_replication.csv"
        replication_status.to_csv(rep_status_path, index=False)
        logger.info(f"  Replication status saved: {rep_status_path}")

    # Power
    power_path = results_dir / "metrics_power.csv"
    power_df.to_csv(power_path, index=False)
    logger.info(f"  Power assessment saved: {power_path}")

    # Untestable gene flags
    flag_path = results_dir / "untestable_genes.txt"
    with open(flag_path, "w") as fh:
        fh.write("# Genes in the 20-gene panel not found on one or both platforms\n")
        fh.write("# (no probes mapped to this gene symbol in the GPL annotation)\n\n")
        fh.write(f"Missing from GSE48350 (GPL570):  {missing_primary}\n")
        fh.write(f"Missing from GSE122063 (GPL16699): {missing_rep}\n")
        fh.write(f"\nAll untestable (union): {untestable_genes}\n")
    logger.info(f"  Untestable gene flags saved: {flag_path}")

    # ===================================================================
    # End metadata
    # ===================================================================
    log_run_metadata(logger, seeds=[seed], phase="end")
    logger.info("H002 run complete.")


if __name__ == "__main__":
    main()
