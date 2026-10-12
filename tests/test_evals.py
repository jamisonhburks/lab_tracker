"""Offline tests for the biology eval harness (evals/). No model or network: the LLM judge
and the generation step are stubbed, so these assert the harness's own logic — dataset
loading, bootstrap/paired statistics, multi-vote median aggregation, and per-item scoring."""

import pytest

import llm
from evals import _dataset, _scorer
from evals import hypothesis_generation as hg


# --- dataset loading ----------------------------------------------------------------------
def test_research_questions_dataset_is_wellformed():
    items = _dataset.load("research_questions_v1.jsonl")
    assert len(items) >= 15                       # the committed ground-truth set
    assert all({"id", "entity_a", "entity_c"} <= set(it) for it in items)
    assert len({it["id"] for it in items}) == len(items)      # ids unique


def test_dataset_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        _dataset.load("does_not_exist_v9.jsonl")


# --- statistics ---------------------------------------------------------------------------
def test_bootstrap_ci_degenerate_and_spread():
    assert _scorer.bootstrap_ci([2, 2, 2, 2]) == [2.0, 2.0]    # no variance -> point CI
    lo, hi = _scorer.bootstrap_ci([0, 1, 2, 1, 2, 0, 1, 2])
    assert lo <= hi and 0.0 <= lo and hi <= 2.0


def test_paired_delta_ci_detects_uniform_lift():
    d = _scorer.paired_delta_ci([1, 1, 1, 1], [2, 2, 2, 2])
    assert d["delta"] == 1.0 and d["ci"] == [1.0, 1.0] and d["p_two_sided"] == 0.0


def test_paired_delta_ci_drops_unaligned_pairs():
    d = _scorer.paired_delta_ci([1, None, 1], [2, 2, None])
    assert d["n"] == 1                            # only the first pair is complete


# --- multi-vote judge aggregation ---------------------------------------------------------
def test_judge_takes_median_and_matching_reason(monkeypatch):
    from pydantic import BaseModel

    class S(BaseModel):
        specificity: int = 0
        specificity_reason: str = ""

    ballots = iter([
        S(specificity=0, specificity_reason="low"),
        S(specificity=2, specificity_reason="high"),
        S(specificity=2, specificity_reason="high-again"),
    ])
    monkeypatch.setattr(llm, "parse", lambda *a, **k: next(ballots))
    out = _scorer.judge("p", {}, S, numeric_fields=["specificity"], votes=3)
    assert out["specificity"] == 2                             # median of {0,2,2}
    assert out["specificity_reason"] in ("high", "high-again")  # reason from a median ballot
    assert len(out["_ballots"]) == 3


def test_judge_survives_a_dead_call(monkeypatch):
    from pydantic import BaseModel

    class S(BaseModel):
        x: int = 0

    def boom(*a, **k):
        raise RuntimeError("judge down")
    monkeypatch.setattr(llm, "parse", boom)
    out = _scorer.judge("p", {}, S, numeric_fields=["x"], votes=3)
    assert out["x"] == 0                          # failed ballots score 0, no crash


# --- per-item scoring (generation + judge stubbed) ----------------------------------------
def test_score_item_composite_and_grounding_mapping(monkeypatch):
    monkeypatch.setattr(hg.agent, "synthesize_hypothesis", lambda a, c, **k: {
        "ok": True, "a_name": a, "c_name": c, "grounding": "weakly_grounded",
        "top_mechanism": "IL6", "hypothesis": {"hypothesis": "h", "mechanisms": []}})
    monkeypatch.setattr(hg._scorer, "judge", lambda *a, **k: {
        "specificity": 2, "testability": 1, "specificity_reason": "", "testability_reason": ""})
    rec = hg.score_item({"id": "x", "entity_a": "A", "entity_c": "C"}, "baseline")
    assert rec["specificity"] == 2 and rec["testability"] == 1
    assert rec["composite"] == 1.5                 # mean(2, 1)
    assert rec["grounding_score"] == 1             # weakly_grounded -> 1


def test_score_item_records_generation_failure(monkeypatch):
    monkeypatch.setattr(hg.agent, "synthesize_hypothesis", lambda a, c, **k: {
        "ok": False, "error": "not in KG"})
    rec = hg.score_item({"id": "x", "entity_a": "A", "entity_c": "C"}, "baseline")
    assert rec["ok"] is False and rec["composite"] is None
