"""confidence — independence-weighted aggregation (A1).

Characterizes both the unchanged behavior (independent sources sum fully) and the new discount
(same research_group => correlated => diminishing 1/sqrt(rank)).
"""
import math

import confidence
from kg_schema import Association, Direction, EpistemicType, Evidence


def _assoc(evidence, predicate="associates"):
    a = Association(subject="A", predicate=predicate, object="B")
    a.evidence = evidence
    return a


def _ev(power, group=None, direction=Direction.SUPPORTS):
    return Evidence(source="s", power=power, research_group=group, direction=direction)


def test_definitional_short_circuits():
    a = Association(subject="X", predicate="is_a", object="Y",
                    epistemic_type=EpistemicType.DEFINITIONAL)
    r = confidence.score_association(a)
    assert r.confidence == 1.0 and r.status == "definitional"


def test_independent_sources_sum_fully_unchanged():
    # No research_group => each independent => plain sum (behavior preserved for today's data).
    r = confidence.score_association(_assoc([_ev(1.0), _ev(1.0), _ev(1.0)]))
    assert math.isclose(r.support, 3.0, abs_tol=1e-3)
    assert r.status == "supported"


def test_same_group_evidence_is_discounted():
    r = confidence.score_association(_assoc([_ev(1.0, "Smith"), _ev(1.0, "Smith"), _ev(1.0, "Smith")]))
    expected = 1 / math.sqrt(1) + 1 / math.sqrt(2) + 1 / math.sqrt(3)
    assert math.isclose(r.support, expected, abs_tol=1e-3)
    assert r.support < 3.0            # three same-lab papers count for less than three independent


def test_mixed_groups_count_each_group_separately():
    r = confidence.score_association(_assoc([_ev(1.0, "Smith"), _ev(1.0, "Smith"), _ev(1.0, "Jones")]))
    expected = (1 / math.sqrt(1) + 1 / math.sqrt(2)) + 1 / math.sqrt(1)   # Smith(2) + Jones(1)
    assert math.isclose(r.support, expected, abs_tol=1e-3)


def test_correlated_nulls_refute_less_than_independent_nulls():
    indep = _assoc([_ev(1.0, None, Direction.REFUTES) for _ in range(3)])
    grouped = _assoc([_ev(1.0, "Smith", Direction.REFUTES) for _ in range(3)])
    assert confidence.score_association(indep).refute > confidence.score_association(grouped).refute


def test_strongest_in_group_keeps_full_weight():
    # Ordering within a group is by informativeness desc: the best study is never discounted.
    r = confidence.score_association(_assoc([_ev(0.2, "Smith"), _ev(0.9, "Smith")]))
    expected = 0.9 / math.sqrt(1) + 0.2 / math.sqrt(2)
    assert math.isclose(r.support, expected, abs_tol=1e-3)


# ---- A2: Beta posterior mean + credible interval ------------------------------------------ #
def test_confidence_is_the_beta_posterior_mean():
    # 3 independent supporting studies (power 1.0): Beta(0.5+3, 0.5) -> mean 3.5/4.0.
    r = confidence.score_association(_assoc([_ev(1.0), _ev(1.0), _ev(1.0)]))
    assert math.isclose(r.confidence, 3.5 / 4.0, abs_tol=1e-3)


def test_credible_interval_brackets_the_mean():
    r = confidence.score_association(_assoc([_ev(1.0), _ev(1.0), _ev(1.0)]))
    assert 0.0 <= r.ci_low <= r.confidence <= r.ci_high <= 1.0
    assert r.ci_high > r.ci_low


def test_more_evidence_tightens_the_interval():
    few = confidence.score_association(_assoc([_ev(1.0) for _ in range(2)]))
    many = confidence.score_association(_assoc([_ev(1.0) for _ in range(8)]))
    assert (many.ci_high - many.ci_low) < (few.ci_high - few.ci_low)


def test_definitional_interval_is_degenerate():
    a = Association(subject="X", predicate="is_a", object="Y",
                    epistemic_type=EpistemicType.DEFINITIONAL)
    r = confidence.score_association(a)
    assert r.confidence == 1.0 and r.ci_low == 1.0 and r.ci_high == 1.0


def test_untested_grounded_edge_is_wide_and_uncertain():
    # A grounded-but-unstudied edge: the prior lifts the mean, but the interval stays honestly wide.
    r = confidence.score_association(_assoc([]), prior=0.5)
    assert r.status in ("promising_but_poorly_tested", "under_investigated")
    assert r.recommend_retest is True
    assert (r.ci_high - r.ci_low) > 0.4
