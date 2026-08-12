"""Hypothesis assessment tools, grounded in the knowledge graph.

Both read the KG (via kg_memory) rather than the model's intuition:
  - assess_hypothesis(a, c)   -> a heuristic realism score from KG path structure
  - propose_experiment(a, c)  -> what data / methods / tests would test the link,
                                 inferred from the mechanism types on the paths

The realism score is a lite version of the Rephetio degree-weighted-path-count
idea: a link is more believable when many short, independently-sourced paths
connect the two entities. It is explicitly a heuristic, not a calibrated
probability.
"""

import math

from kg_memory import _index, _label, enumerate_paths

W_DEG = 0.4   # hub penalty exponent for degree-weighted path count (Rephetio-style)


def _atomic_sources(paths) -> set:
    """Distinct sources, splitting compound 'A, B' source strings into atoms."""
    out = set()
    for p in paths:
        for (_, _, _, src, _) in p:
            out.update(t.strip() for t in src.split(",") if t.strip())
    return out


def assess_hypothesis(entity_a: str, entity_c: str, max_len: int = 3) -> str:
    """Score how well the KG supports a hypothesized link between two entities.

    Uses a degree-weighted path count: paths through HUB nodes (high-degree genes,
    drugs) count for little, so a link earns its score from short, specific,
    independently-sourced paths — not from being reachable via everything.
    """
    a, c, paths, truncated = enumerate_paths(entity_a, entity_c, max_len=max_len)
    if a is None or c is None:
        missing = entity_a if a is None else entity_c
        return f"'{missing}' not found in the knowledge graph."
    if not paths:
        return (f"Realism 0.00 (unsupported): no KG path connects "
                f"{_label(a)} and {_label(c)} within {max_len} hops.")

    adj = _index()
    def _deg(n):
        return max(1, len(adj.get(n, [])))

    def _weight(p):                             # 1.0 for a direct edge; hub-mediated
        nodes = [p[0][0]] + [e[4] for e in p]   # paths shrink toward 0
        w = 1.0
        for mid in nodes[1:-1]:                 # internal (non-endpoint) nodes only
            w /= _deg(mid) ** W_DEG
        return w

    weights = [_weight(p) for p in paths]
    best, dwpc = max(weights), sum(weights)     # specificity + abundance
    sources = _atomic_sources(paths)
    realism = 1 - math.exp(-(2.0 * best + 0.15 * dwpc + 0.05 * len(sources)))

    shortest = min(len(p) for p in paths)
    label = ("well-supported" if realism >= 0.75 else
             "plausible" if realism >= 0.5 else
             "weak" if realism >= 0.25 else "speculative")

    return "\n".join([
        f"Realism {realism:.2f} ({label}) — {_label(a)} <-> {_label(c)}",
        f"  supporting paths: {len(paths)}{'+' if truncated else ''} "
        f"(shortest {shortest} hop{'s' if shortest > 1 else ''}"
        f"{', direct edge' if shortest == 1 else ''})",
        f"  degree-weighted support: best {best:.2f}, total {dwpc:.2f}",
        f"  independent sources: {len(sources)} ({', '.join(sorted(sources))[:160]})",
        "  NOTE: heuristic (degree-weighted path count) — comparative, not a",
        "  calibrated probability; true calibration needs a permutation null.",
    ])


# Mechanism (edge predicate) -> (study design, data needed, statistical test).
# Keys are lowercased and matched by substring so it works across KG vocabularies.
_DESIGNS = {
    "associat": ("genetic association study",
                 "genotyped cohort with case/control disease labels",
                 "case-control GWAS / logistic regression; Mendelian randomization for causality"),
    "regulat": ("differential expression study",
                "case vs. control tissue or blood (RNA-seq / microarray)",
                "differential expression (DESeq2/limma) with FDR control; qPCR validation"),
    "treat": ("interventional study",
              "randomized trial arms, or an EHR cohort for target-trial emulation",
              "RCT (intention-to-treat), or propensity-matched survival analysis"),
    "palliat": ("interventional study",
                "randomized arms or matched observational cohort",
                "RCT or propensity-matched outcome analysis"),
    "resembl": ("shared-etiology comparative study",
                "two disease cohorts with matched controls (genotype + expression)",
                "genetic correlation (LDSC) and cross-disease transcriptomic overlap"),
    "present": ("clinical phenotyping study",
                "structured clinical records / disease registry",
                "prevalence and phenotype-association testing"),
    "localiz": ("anatomical/expression-localization study",
                "tissue-level expression atlas or imaging",
                "spatial/tissue enrichment testing"),
    "bind": ("molecular interaction assay",
             "purified proteins or cell lines",
             "co-IP / SPR / reporter assay"),
    "interact": ("molecular interaction assay",
                 "purified proteins or cell lines",
                 "co-IP / SPR / reporter assay"),
}
_GENERIC = ("mechanistic follow-up study",
            "appropriate model system or cohort for this relation",
            "hypothesis-specific test with a pre-registered analysis plan")


def propose_experiment(entity_a: str, entity_c: str, hypothesis: str = "",
                       max_len: int = 3) -> str:
    """Infer the data, methods, and tests needed to test a hypothesized link."""
    a, c, paths, _ = enumerate_paths(entity_a, entity_c, max_len=max_len)
    if a is None or c is None:
        missing = entity_a if a is None else entity_c
        return f"'{missing}' not found in the knowledge graph."

    lines = [f"Test plan for: {_label(a)} <-> {_label(c)}"]
    if hypothesis:
        lines.append(f"Hypothesis: {hypothesis}")

    if not paths:
        lines.append("\nNo mechanistic link in the KG — this is exploratory. A first "
                     "study would need to ESTABLISH a link (e.g. a hypothesis-free "
                     "association scan) before mechanism-specific tests apply.")
    else:
        predicates = {pred for p in paths for (_, pred, _, _, _) in p}
        lines.append(f"\nMechanisms implicated by the KG paths: {', '.join(sorted(predicates))}")
        lines.append("\nRecommended studies (one per implicated mechanism):")
        seen = set()
        for pred in sorted(predicates):
            design, data, test = next(
                (v for k, v in _DESIGNS.items() if k in pred.lower()), _GENERIC)
            if design in seen:
                continue
            seen.add(design)
            lines.append(f"- [{pred}] {design}")
            lines.append(f"    data:  {data}")
            lines.append(f"    test:  {test}")

    lines += [
        "\nDesign essentials:",
        f"- exposure -> outcome: {_label(a)} -> {_label(c)}",
        "- controls & confounders: age, sex, ancestry, batch",
        "- multiple testing: report BOTH Bonferroni and Benjamini-Hochberg FDR",
        "- report effect size + 95% CI alongside p-values",
        "- power: size the cohort for the target effect; >=3 runs for stochastic models",
    ]
    return "\n".join(lines)
