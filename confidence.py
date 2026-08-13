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

Heuristic and interpretable, not a calibrated probability — true calibration
would need a labeled outcome set. Thresholds below are tunable.
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


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-1.2 * x))


@dataclass
class ConfidenceResult:
    confidence: float
    status: str
    support: float
    refute: float
    investigation: float
    recommend_retest: bool
    explanation: str

    def render(self) -> str:
        retest = "yes" if self.recommend_retest else "no"
        return "\n".join([
            f"Confidence {self.confidence:.2f} ({self.status}) — re-test: {retest}",
            f"  support {self.support:.2f} | refute {self.refute:.2f} "
            f"(power-weighted) | investigation {self.investigation:.2f}",
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


def score_association(assoc: Association, prior: float = 0.0) -> ConfidenceResult:
    """Aggregate evidence into a confidence + status. `prior` is an optional
    structural belief (e.g. the KG realism score) that a mechanism plausibly exists."""
    if assoc.is_definitional:
        return ConfidenceResult(1.0, "definitional", 1.0, 0.0, 1.0, False,
                                _EXPLAIN["definitional"])

    support = prior + sum(e.informativeness() for e in assoc.supporting())
    refute = sum(e.informativeness() for e in assoc.refuting())   # underpowered ~ 0
    investigation = sum(e.informativeness() for e in assoc.evidence)
    net = support - refute

    if investigation < INVEST_FLOOR:
        # barely tested — uncertainty dominates; don't let thin negatives "refute"
        status = ("promising_but_poorly_tested" if support >= BELIEF_FLOOR
                  else "under_investigated")
        confidence = 0.45 + 0.10 * min(support, 1.0)   # ~0.45–0.55, high uncertainty
        recommend = True
    elif refute >= INVEST_FLOOR and net <= -0.5:
        status, confidence, recommend = "refuted", _sigmoid(net), False
    elif support >= INVEST_FLOOR and refute >= INVEST_FLOOR:
        status, confidence, recommend = "contested", _sigmoid(net), True
    elif net >= 0.5:
        status, confidence, recommend = "supported", _sigmoid(net), False
    else:
        status, confidence, recommend = "under_investigated", _sigmoid(net), True

    return ConfidenceResult(round(confidence, 3), status, round(support, 3),
                            round(refute, 3), round(investigation, 3), recommend,
                            _EXPLAIN[status])


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
