#!/usr/bin/env python3
"""H003 — pre-registered statistical comparison (interpreter, not executor).

Reads the per-seed metrics written by run.py (results/metrics.csv, long format
arm,label,seed,metric,value) and evaluates the hypothesis's success_metric:

  PRIMARY (calibration + truthfulness): for BOTH substrate contrasts —
    b vs a  (qwen3:14b  +substrate vs bare)
    d vs c  (frontier   +substrate vs bare)
  the substrate arm shows LOWER ece, confidently_wrong_rate, hallucination_rate,
  with a negative paired effect size (Cohen's d_z) that survives Bonferroni AND
  Benjamini-Hochberg FDR across the family of arm comparisons.

  SECONDARY: (b vs a) ranking (auroc/auprc) does not materially degrade, and
  per-grounding-grade mean confidence is monotone (grounded > weakly_grounded >
  novel_unverified) within the substrate arms.

This script does NOT re-run the experiment. It only reads results and writes
results/stats.csv + results/stats_report.md. Run after run.py has ≥3 seeds:

    python experiments/H003_substrate_lift/stats.py
    python experiments/H003_substrate_lift/stats.py --metrics /path/to/metrics.csv   # e.g. a self-test
"""
import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

EXP = Path(__file__).resolve().parent

# lower-is-better calibration/truthfulness metrics — the substrate's core claim
PRIMARY_METRICS = ["ece", "confidently_wrong_rate", "hallucination_rate"]
# (substrate_arm, bare_arm, human label)
CONTRASTS = [("b", "a", "qwen3:14b +substrate vs bare"),
             ("d", "c", "frontier +substrate vs bare")]
SECONDARY_METRICS = ["auroc", "auprc"]          # want NOT materially worse (b vs a)
MATERIAL = 0.05                                  # a drop larger than this is "material" degradation
GRADE_ORDER = ["grounded", "weakly_grounded", "novel_unverified"]


# --------------------------------------------------------------------------- #
# IO                                                                            #
# --------------------------------------------------------------------------- #
def load_metrics(path: Path):
    """-> {(arm, metric): {seed: value}}, plus {arm: label}."""
    vals = defaultdict(dict)
    labels = {}
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            arm, metric, seed = r["arm"], r["metric"], int(r["seed"])
            labels[arm] = r["label"]
            try:
                vals[(arm, metric)][seed] = float(r["value"])
            except ValueError:
                pass
    return vals, labels


def load_by_grade(path: Path):
    """-> {(arm, grade): mean_conf}."""
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[(r["arm"], r["grade"])] = float(r["mean_conf"])
    return out


# --------------------------------------------------------------------------- #
# Paired stats (no scipy/statsmodels dependency for the core math; both are     #
# available per CLAUDE.md but we keep the arithmetic explicit and auditable)    #
# --------------------------------------------------------------------------- #
def _mean(xs):
    return sum(xs) / len(xs)


def _sd(xs, ddof=1):
    n = len(xs)
    if n - ddof <= 0:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - ddof))


def paired_t(diffs):
    """Paired t-test on the per-seed differences (substrate - bare).

    Returns (t, p_two_sided, cohen_dz). Handles the degenerate small-n cases that
    a 3-seed pre-registered design routinely hits:
      * all diffs identical & non-zero -> deterministic effect (t=inf, p->0)
      * all diffs zero                  -> no effect (t=0, p=1)
    """
    n = len(diffs)
    md, sd = _mean(diffs), _sd(diffs)
    if n < 2:
        return (float("nan"), float("nan"), float("nan"))
    if sd == 0.0:
        if md == 0.0:
            return (0.0, 1.0, 0.0)
        # zero within-pair variance, non-zero mean: a perfectly consistent effect.
        return (float("inf") * (1 if md > 0 else -1), 0.0, float("inf") * (1 if md > 0 else -1))
    dz = md / sd                                   # Cohen's d_z (paired)
    t = md / (sd / math.sqrt(n))
    # two-sided p via the t distribution survival function
    from scipy.stats import t as tdist            # scipy is in the core stack
    p = 2.0 * tdist.sf(abs(t), df=n - 1)
    return (t, float(p), dz)


def bonferroni(pvals):
    m = len(pvals)
    return [min(1.0, p * m) if not math.isnan(p) else p for p in pvals]


def benjamini_hochberg(pvals):
    """BH-FDR adjusted p-values, NaN-safe (NaNs excluded from ranking, passed through)."""
    idx = [i for i, p in enumerate(pvals) if not math.isnan(p)]
    m = len(idx)
    out = [float("nan")] * len(pvals)
    if m == 0:
        return out
    order = sorted(idx, key=lambda i: pvals[i])
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):   # largest p first
        k = m - rank + 1                                   # its ascending rank
        adj = min(prev, pvals[i] * m / k)
        out[i] = adj
        prev = adj
    return out


# --------------------------------------------------------------------------- #
# Main                                                                          #
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", default=str(EXP / "results" / "metrics.csv"))
    ap.add_argument("--by-grade", default=str(EXP / "results" / "metrics_by_grade.csv"))
    ap.add_argument("--out-csv", default=str(EXP / "results" / "stats.csv"))
    ap.add_argument("--out-md", default=str(EXP / "results" / "stats_report.md"))
    ap.add_argument("--alpha", type=float, default=0.05)
    args = ap.parse_args()

    mpath = Path(args.metrics)
    if not mpath.exists():
        raise SystemExit(f"metrics file not found: {mpath} — run run.py first")
    vals, labels = load_metrics(mpath)
    by_grade = load_by_grade(Path(args.by_grade))

    # seeds present per arm (a metric that exists for an arm shares the arm's seed set)
    def seeds_for(arm):
        s = set()
        for (a, _m), d in vals.items():
            if a == arm:
                s |= set(d.keys())
        return sorted(s)

    lines = []                      # markdown report
    csv_rows = [["contrast", "metric", "n_seeds", "mean_bare", "mean_substrate",
                 "mean_diff", "cohen_dz", "p_raw", "p_bonferroni", "p_bh",
                 "direction_ok", "sig_bonf", "sig_bh"]]

    def w(s=""):
        lines.append(s)

    w("# H003 — pre-registered statistical comparison")
    w()
    w(f"Source: `{mpath}`  ·  α = {args.alpha}")
    w()

    # ---- PRIMARY: paired tests across the family, then multiplicity correction ----
    family = []          # (contrast_label, metric, n, mean_bare, mean_sub, diff, dz, p)
    for sub, bare, clabel in CONTRASTS:
        sub_seeds, bare_seeds = set(seeds_for(sub)), set(seeds_for(bare))
        common = sorted(sub_seeds & bare_seeds)
        if not common:
            continue
        for metric in PRIMARY_METRICS:
            sv, bv = vals.get((sub, metric), {}), vals.get((bare, metric), {})
            paired = [(sv[s], bv[s]) for s in common if s in sv and s in bv]
            if not paired:
                continue
            diffs = [x - y for x, y in paired]           # substrate - bare (want < 0)
            n = len(diffs)
            mean_sub = _mean([x for x, _ in paired])
            mean_bare = _mean([y for _, y in paired])
            _t, p, dz = paired_t(diffs)
            family.append([clabel, metric, n, mean_bare, mean_sub, _mean(diffs), dz, p])

    p_raw = [row[7] for row in family]
    p_bonf = bonferroni(p_raw)
    p_bh = benjamini_hochberg(p_raw)

    w("## PRIMARY — calibration & truthfulness (lower is better; want substrate < bare)")
    w()
    w(f"Family of {len(family)} paired tests "
      f"({len(CONTRASTS)} contrasts × {len(PRIMARY_METRICS)} metrics), "
      f"corrected across the family (Bonferroni + BH-FDR).")
    w()
    w("| contrast | metric | n | bare | +substrate | Δ (sub−bare) | Cohen dz | p | p_bonf | p_BH | dir? | sig(bonf) | sig(BH) |")
    w("|---|---|--:|--:|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|")
    primary_ok = bool(family)
    for i, (clabel, metric, n, mb, ms, diff, dz, p) in enumerate(family):
        dir_ok = diff < 0                       # substrate lowers the (bad) metric
        sig_b = (not math.isnan(p_bonf[i])) and p_bonf[i] < args.alpha
        sig_h = (not math.isnan(p_bh[i])) and p_bh[i] < args.alpha
        # a metric with no variation (e.g. hallucination 0 everywhere) is degenerate, not a pass/fail
        degenerate = (diff == 0.0 and dz == 0.0)
        if not degenerate and not (dir_ok and sig_b and sig_h):
            primary_ok = False
        csv_rows.append([clabel, metric, n, round(mb, 4), round(ms, 4), round(diff, 4),
                         round(dz, 4) if math.isfinite(dz) else dz,
                         round(p, 5) if math.isfinite(p) else p,
                         round(p_bonf[i], 5) if math.isfinite(p_bonf[i]) else p_bonf[i],
                         round(p_bh[i], 5) if math.isfinite(p_bh[i]) else p_bh[i],
                         dir_ok, sig_b, sig_h])
        def fnum(x):
            return f"{x:.3f}" if isinstance(x, float) and math.isfinite(x) else str(x)
        w(f"| {clabel} | {metric} | {n} | {fnum(mb)} | {fnum(ms)} | {diff:+.3f} | "
          f"{fnum(dz)} | {fnum(p)} | {fnum(p_bonf[i])} | {fnum(p_bh[i])} | "
          f"{'✓' if dir_ok else '✗'} | {'✓' if sig_b else '·'} | {'✓' if sig_h else '·'} |"
          + ("  _(no variation)_" if degenerate else ""))
    w()

    # ---- SECONDARY: ranking must not materially degrade (b vs a) ----
    w("## SECONDARY — ranking must not materially degrade (qwen3:14b b vs a)")
    w()
    common_ba = sorted(set(seeds_for("b")) & set(seeds_for("a")))
    ranking_ok = True
    if common_ba:
        w("| metric | a (bare) | b (+substrate) | Δ | material drop? |")
        w("|---|--:|--:|--:|:--:|")
        for metric in SECONDARY_METRICS:
            av, bv = vals.get(("a", metric), {}), vals.get(("b", metric), {})
            paired = [(bv[s], av[s]) for s in common_ba if s in av and s in bv]
            if not paired:
                continue
            mb, ma = _mean([x for x, _ in paired]), _mean([y for _, y in paired])
            drop = (mb - ma) < -MATERIAL
            if drop:
                ranking_ok = False
            w(f"| {metric} | {ma:.3f} | {mb:.3f} | {mb-ma:+.3f} | {'⚠︎ yes' if drop else 'no'} |")
    else:
        w("_arms a/b not both present — skipped._")
    w()

    # ---- SECONDARY: per-grade confidence monotonicity within substrate arms ----
    w("## SECONDARY — per-grade confidence monotonicity (want grounded > weakly_grounded > novel_unverified)")
    w()
    mono_ok = True
    any_grade = False
    w("| arm | grounded | weakly_grounded | novel_unverified | monotone? |")
    w("|---|--:|--:|--:|:--:|")
    for arm in ("b", "d"):
        confs = [by_grade.get((arm, g)) for g in GRADE_ORDER]
        present = [c for c in confs if c is not None]
        if len(present) < 2:
            continue
        any_grade = True
        seq = [c for c in confs if c is not None]
        is_mono = all(earlier >= later for earlier, later in zip(seq, seq[1:]))
        if not is_mono:
            mono_ok = False
        cells = " | ".join(f"{c:.3f}" if c is not None else "—" for c in confs)
        w(f"| {arm} | {cells} | {'✓' if is_mono else '✗'} |")
    if not any_grade:
        w("| _(no per-grade data)_ | | | | |")
    w()

    # ---- overall verdict ----
    n_seeds_present = max((len(seeds_for(a)) for a in ("a", "b", "c", "d")), default=0)
    w("## Verdict")
    w()
    if n_seeds_present < 3:
        w(f"⚠️  **Underpowered — only {n_seeds_present} seed(s) present.** The pre-registered "
          f"design requires ≥3 (CLAUDE.md `min_runs`). Numbers below are descriptive only; the "
          f"paired tests are not valid until ≥3 seeds are run.")
    else:
        verdict = ("**SUPPORTED**" if (primary_ok and ranking_ok) else
                   "**NOT SUPPORTED / FALSIFIED**")
        w(f"- Primary (calibration/truthfulness, both contrasts survive Bonferroni+BH): "
          f"{'✓' if primary_ok else '✗'}")
        w(f"- Secondary (ranking not materially degraded): {'✓' if ranking_ok else '✗'}")
        w(f"- Secondary (per-grade confidence monotone): {'✓' if mono_ok else '✗ (or n/a)'}")
        w()
        w(f"### {verdict}")
        w()
        w("_Note: with n=3 seeds the paired tests are low-power; a non-significant result is weak "
          "evidence, not proof of no effect. Report effect sizes (Cohen's dz) alongside p-values._")
    w()

    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    with Path(args.out_csv).open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(csv_rows)

    print("\n".join(lines))
    print(f"\nwrote {args.out_csv}\nwrote {args.out_md}")


if __name__ == "__main__":
    main()
