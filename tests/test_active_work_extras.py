"""Active-work Phase B: pre-registration guardrail (#5), decision log (#6), evidence bridge (#3),
sanity-check (#4). Hermetic — HYP/EXP redirected to tmp_path; contribute/match_misc/novelty stubbed.
"""
import contribute
import misc_research
import worklog


def _write_spec(tmp_path, min_runs=1, status="approved", success="metric-A"):
    (tmp_path / "hypotheses" / "H001_demo.yaml").write_text(
        f'id: H001\ntitle: "Demo"\nsuccess_metric: "{success}"\n'
        f"min_runs: {min_runs}\nstatus: {status}\n", encoding="utf-8")


def _isolate(tmp_path, monkeypatch, **spec):
    monkeypatch.setattr(worklog, "EXP", tmp_path / "experiments")
    monkeypatch.setattr(worklog, "HYP", tmp_path / "hypotheses")
    (tmp_path / "hypotheses").mkdir()
    _write_spec(tmp_path, **spec)


# ---- #5 pre-registration guardrail -------------------------------------------------------- #
def test_prereg_snapshot_then_drift_detection(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, success="original metric")
    worklog.log_run("H001", metrics={"x": 1}, seed=1)          # snapshots the success_metric
    assert worklog.preregistration("H001")["drift"] is False
    _write_spec(tmp_path, success="changed metric")            # move the goalposts post-hoc
    assert worklog.preregistration("H001")["drift"] is True
    assert "DRIFT" in worklog.status("H001")


# ---- #6 decision log ---------------------------------------------------------------------- #
def test_log_decision_and_status_count(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    worklog.log_decision("H001", "dropped 3 outlier samples", "flagged by QC")
    assert len(worklog.decisions("H001")) == 1
    worklog.log_run("H001", metrics={"x": 1}, seed=1)
    assert "decisions logged: 1" in worklog.status("H001")


# ---- #3 evidence bridge ------------------------------------------------------------------- #
def test_evidence_bundle_not_ready_without_provenance(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, min_runs=1)
    worklog.log_run("H001", metrics={"cohens_d": 0.8}, seed=1, passed=True, valid=True)
    b = worklog.evidence_bundle("H001")
    assert b["ready"] is False and "provenance" in b["reason"]


def test_evidence_bundle_ready_and_aggregates(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, min_runs=2)
    for s in (1, 2):
        worklog.log_run("H001", metrics={"cohens_d": 0.8, "p_bh": 0.01}, seed=s, passed=True, valid=True)
    (worklog._exp_dir("H001") / "provenance.md").write_text("prov", encoding="utf-8")
    b = worklog.evidence_bundle("H001")
    assert b["ready"] is True and b["direction"] == "supports"
    assert b["effect_size"] == 0.8 and b["p_value"] == 0.01


def test_evidence_bundle_blocks_unapproved(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, status="draft")
    worklog.log_run("H001", metrics={"cohens_d": 0.8}, seed=1, passed=True, valid=True)
    assert worklog.evidence_bundle("H001")["ready"] is False


def test_contribute_result_routes_when_ready(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, min_runs=1)
    worklog.log_run("H001", metrics={"cohens_d": 0.8, "p_bh": 0.01}, seed=1, passed=True, valid=True)
    (worklog._exp_dir("H001") / "provenance.md").write_text("prov", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(contribute, "contribute", lambda *a, **k: captured.update(k) or "routed")
    out = contribute.contribute_result("H001", "geneX", "differentially_expressed_in", "AD brain")
    assert out == "routed"
    assert captured["source_kind"] == "experiment" and captured["source"] == "experiment:H001"
    assert captured["direction"] == "supports" and captured["effect_size"] == 0.8


def test_contribute_result_blocks_when_not_ready(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, min_runs=3)               # only 1 run < min_runs
    worklog.log_run("H001", metrics={"cohens_d": 0.8}, seed=1, passed=True, valid=True)
    assert "not ready" in contribute.contribute_result("H001", "a", "b", "c")


# ---- #4 sanity-check ---------------------------------------------------------------------- #
def test_sanity_check_composes_three_signals(monkeypatch):
    monkeypatch.setattr(misc_research, "match_misc",
                        lambda s, o, c="": {"verdict": "grounded_but_uncurated", "grounding": "grounded"})
    monkeypatch.setattr("deadends.render_check", lambda s, o, a: "prior dead-end: X failed")
    monkeypatch.setattr("novelty.check_novelty", lambda a, c, via="": "novel_juxtaposition")
    out = misc_research.sanity_check("geneX up in AD", subject="geneX", object="AD")
    assert "vs lab knowledge: grounded_but_uncurated" in out
    assert "dead-ends: prior dead-end" in out
    assert "novelty: novel_juxtaposition" in out
