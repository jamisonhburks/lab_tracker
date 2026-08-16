"""confidence — power-weighted evidence aggregation for associations (phase 4).

Turns an Association's supporting/refuting Evidence (plus an optional structural
prior, e.g. the KG realism score) into a confidence in [0,1] AND a status that
the raw number can't express:

  definitional | supported | refuted | contested
  under_investigated | promising_but_poorly_tested

The load-bearing idea: refuting studies are weighted by `informativeness()`
(≈ power / methodology quality), so an UNDERPOWERED null barely counts against a
hypothesis. A link that only *looks* negative because the negatives were poorly
powered is flagged `promising_but_poorly_tested` with a re-test recommendation —
not buried as `refuted`. (Absence of evidence != evidence of absence.)

Independence weighting: studies sharing a `research_group` (last author) are correlated,
so evidence is grouped and only the strongest in each group counts fully — each additional
same-group study adds a diminishing `1/sqrt(rank)`. Studies with no known group are treated
as independent (we don't assume correlation), so three papers from one lab move belief less
than three papers from three labs. This is inert until `research_group` is populated, then it
engages automatically.

Confidence is the mean of a Beta posterior over supporting vs refuting evidence
mass, and it carries a credible interval (how *settled* that number is). Still
interpretable, not a calibrated probability — the evidence pseudo-counts are
heuristic and calibration.py audits calibration separately. Thresholds tunable.
"""

import math
from dataclasses import dataclass

from kg_schema import Association

INVEST_FLOOR = 1.0    # total study-power below this => "under-investigated"
BELIEF_FLOOR = 0.25   # some prior/support above this => "promising", not just weak

# KG grounding status -> a structural PRIOR (added to `support` in score_association).
# A trustworthy KG subgraph corroborating a claim raises confidence; 'novel'/'off-graph'
# add nothing (the KG is incomplete — absence isn't evidence against, per B1's humility).
GROUNDING_PRIOR = {
    "grounded": 0.5,
    "weakly_grounded": 0.2,
    "novel_unverified": 0.0,
    "off_graph": 0.0,
}


def grounding_prior(status: str) -> float:
    """Map a kg_memory.check_connection status to a confidence prior."""
    return GROUNDING_PRIOR.get(status, 0.0)


try:                                              # exact Beta credible interval when SciPy is present
    from scipy.stats import beta as _scipy_beta
except Exception:                                 # pragma: no cover - SciPy optional
    _scipy_beta = None

PRIOR = 0.5   # Jeffreys Beta(0.5,0.5) prior: an untested edge stays honestly uncertain, evidence dominates


def _posterior(support: float, refute: float) -> tuple:
    """Beta(alpha, beta) over 'the association holds', from independence-weighted evidence mass
    (support/refute act as pseudo-counts) plus the weak Jeffreys prior."""
    return PRIOR + max(0.0, support), PRIOR + max(0.0, refute)


def _credible_interval(alpha: float, beta: float, cred: float = 0.90) -> tuple:
    """A `cred` credible interval for Beta(alpha, beta) — how *settled* the confidence is. Exact via
    SciPy; else a clipped normal approximation (rough at the extremes, but conveys the width)."""
    tail = (1.0 - cred) / 2.0
    if _scipy_beta is not None:
        return (float(_scipy_beta.ppf(tail, alpha, beta)),
                float(_scipy_beta.ppf(1.0 - tail, alpha, beta)))
    mean = alpha / (alpha + beta)
    sd = math.sqrt(alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1.0)))
    return max(0.0, mean - 1.645 * sd), min(1.0, mean + 1.645 * sd)


@dataclass
class ConfidenceResult:
    confidence: float
    status: str
    support: float
    refute: float
    investigation: float
    recommend_retest: bool
    explanation: str
    ci_low: float = 0.0
    ci_high: float = 1.0

    def render(self) -> str:
        retest = "yes" if self.recommend_retest else "no"
        return "\n".join([
            f"Confidence {self.confidence:.2f} [{self.ci_low:.2f}–{self.ci_high:.2f} CI] "
            f"({self.status}) — re-test: {retest}",
            f"  support {self.support:.2f} | refute {self.refute:.2f} "
            f"(independence-weighted) | investigation {self.investigation:.2f}",
            f"  {self.explanation}",
        ])


_EXPLAIN = {
    "definitional": "Definitional/ontological edge — true within the ontology.",
    "supported": "Adequately investigated and the net evidence supports the link.",
    "refuted": "Adequately investigated with well-powered nulls — genuine evidence "
               "of absence.",
    "contested": "Strong evidence on both sides — genuinely disputed.",
    "under_investigated": "Too little study power applied to conclude anything; "
                          "the link is essentially untested.",
    "promising_but_poorly_tested": "The net evidence looks negative, but the "
        "refuting studies are underpowered/biased and total investigation is thin "
        "— the negative may be a methodology artifact. A well-powered test is "
        "warranted (use propose_experiment to size the cohort).",
}


def _weighted_mass(evidence: list) -> float:
    """Independence-weighted sum of study informativeness.

    Studies sharing a `research_group` are correlated: within a group the strongest counts fully
    and each additional same-group study contributes a diminishing `1/sqrt(rank)`, so N papers
    from one lab don't count as N independent corroborations. Evidence with no known group is
    treated as its OWN group (we don't assume unknown sources are correlated) — so this equals a
    plain sum until the independence signal is populated, then it discounts automatically.
    """
    groups: dict = {}
    for i, e in enumerate(evidence):
        key = e.research_group or f"__indep_{i}"      # unknown group => independent (own group)
        groups.setdefault(key, []).append(e.informativeness())
    total = 0.0
    for infs in groups.values():
        for rank, inf in enumerate(sorted(infs, reverse=True), start=1):
            total += inf / math.sqrt(rank)
    return total


def score_association(assoc: Association, prior: float = 0.0) -> ConfidenceResult:
    """Aggregate evidence into a confidence + status + credible interval. `prior` is an optional
    structural belief (e.g. the KG grounding/realism score) that a mechanism plausibly exists.

    Confidence is the MEAN of a Beta posterior over independence-weighted supporting vs refuting
    evidence mass; the [ci_low, ci_high] interval reports how *settled* that number is — two weak
    studies read as a wide interval, many strong ones as a tight one. Status still comes from the
    evidence mass (the qualitative distinctions the raw number can't carry)."""
    if assoc.is_definitional:
        return ConfidenceResult(1.0, "definitional", 1.0, 0.0, 1.0, False,
                                _EXPLAIN["definitional"], 1.0, 1.0)

    support = prior + _weighted_mass(assoc.supporting())
    refute = _weighted_mass(assoc.refuting())     # underpowered ~ 0; same-group correlated ~ discounted
    investigation = _weighted_mass(assoc.evidence)

    alpha, beta = _posterior(support, refute)
    confidence = alpha / (alpha + beta)           # posterior mean
    ci_low, ci_high = _credible_interval(alpha, beta)

    if investigation < INVEST_FLOOR:
        # barely tested — the interval is wide; don't let thin negatives "refute"
        status = ("promising_but_poorly_tested" if support >= BELIEF_FLOOR
                  else "under_investigated")
        recommend = True
    elif refute >= INVEST_FLOOR and confidence <= 0.4:
        status, recommend = "refuted", False
    elif support >= INVEST_FLOOR and refute >= INVEST_FLOOR:
        status, recommend = "contested", True
    elif confidence >= 0.6:
        status, recommend = "supported", False
    else:
        status, recommend = "under_investigated", True

    return ConfidenceResult(round(confidence, 3), status, round(support, 3),
                            round(refute, 3), round(investigation, 3), recommend,
                            _EXPLAIN[status], round(ci_low, 3), round(ci_high, 3))


if __name__ == "__main__":   # three regimes, same net-negative-looking inputs differ
    from kg_schema import Direction, Evidence, RiskOfBias, lift_edge

    def edge(pred="associates"):
        return lift_edge("Gene:5743", pred, "Disease:DOID:8778")

    # A: well-supported — three adequately powered positives
    a = edge()
    a.evidence = [Evidence(source=s, power=0.85) for s in ("GWAS Catalog", "DisGeNET", "OMIM")]

    # B: LOOKS negative, but only underpowered nulls + a plausible mechanism prior
    b = edge()
    b.evidence = [Evidence(source="small cohort", direction=Direction.REFUTES,
                           power=0.15, sample_size=40) for _ in range(3)]

    # C: genuinely refuted — three well-powered nulls
    c = edge()
    c.evidence = [Evidence(source="large RCT", direction=Direction.REFUTES,
                           power=0.9, risk_of_bias=RiskOfBias.LOW) for _ in range(3)]

    print("=== A: adequately-powered positives ===")
    print(score_association(a).render())
    print("\n=== B: only UNDERPOWERED nulls, mechanism prior 0.4 ===")
    print(score_association(b, prior=0.4).render())
    print("\n=== C: well-powered nulls ===")
    print(score_association(c).render())
