"""worklog — the per-hypothesis run ledger + worklog + status view (active-work support).

Hermetic: HYP/EXP are redirected into tmp_path with a stub hypothesis spec, so nothing touches
the repo's real hypotheses/ or experiments/.
"""
import worklog


def _isolate(tmp_path, monkeypatch, min_runs=3, status="approved"):
    monkeypatch.setattr(worklog, "EXP", tmp_path / "experiments")
    monkeypatch.setattr(worklog, "HYP", tmp_path / "hypotheses")
    (tmp_path / "hypotheses").mkdir()
    (tmp_path / "hypotheses" / "H001_demo.yaml").write_text(
        'id: H001\ntitle: "Demo hypothesis"\n'
        'success_metric: ">=3 genes at BH-FDR<0.05"\n'
        f"min_runs: {min_runs}\nstatus: {status}\n", encoding="utf-8")


def test_log_run_and_runs_roundtrip(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    worklog.log_run("H001", metrics={"n_sig": 4, "auc": 0.82}, seed=42, passed=True, valid=True)
    rs = worklog.runs("H001")
    assert len(rs) == 1
    assert rs[0]["seed"] == 42 and rs[0]["metrics"]["n_sig"] == 4 and rs[0]["passed"] is True


def test_run_ledger_keyed_by_bare_id_regardless_of_reference(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    worklog.log_run("H001_demo", metrics={"x": 1})     # referenced by full stem
    worklog.log_run("H001", metrics={"x": 2})          # referenced by bare id
    assert len(worklog.runs("H001")) == 2               # same ledger


def test_stability_summarizes_numeric_metrics(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for s, v in [(1, 4), (2, 5), (3, 3)]:
        worklog.log_run("H001", metrics={"n_sig": v}, seed=s)
    st = worklog.stability("H001")
    assert st["n_sig"]["n"] == 3
    assert st["n_sig"]["min"] == 3 and st["n_sig"]["max"] == 5
    assert abs(st["n_sig"]["mean"] - 4.0) < 1e-9


def test_status_shows_progress_and_next_step_below_min_runs(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    worklog.log_run("H001", metrics={"n_sig": 4}, seed=1, passed=True, valid=True)
    out = worklog.status("H001")
    assert "1/3" in out
    assert "run again with a NEW seed" in out


def test_status_recommends_contribute_when_min_runs_met_and_passing(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for s in (1, 2, 3):
        worklog.log_run("H001", metrics={"n_sig": 4}, seed=s, passed=True, valid=True)
    out = worklog.status("H001")
    assert "3/3" in out
    assert "propose_experiment" in out or "contribute" in out


def test_status_flags_invalidated_run(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    worklog.log_run("H001", metrics={"n_sig": 0}, seed=1, valid=False)
    out = worklog.status("H001")
    assert "INVALID" in out
    assert "fix the pipeline" in out


def test_status_warns_when_hypothesis_not_approved(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, status="draft")
    out = worklog.status("H001")
    assert "draft" in out
    assert "get it approved" in out


def test_note_appends_to_persistent_worklog(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    worklog.note("H001", "tried Welch's t-test — IDE strongest")
    p = worklog._worklog_path("H001")
    assert p.exists()
    body = p.read_text(encoding="utf-8")
    assert "# Worklog — H001" in body and "Welch" in body


# ---- active-work summary for the warm start (#2) ------------------------------------------ #
def test_summary_reports_progress_and_next(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    worklog.log_run("H001", metrics={"n_sig": 4}, seed=1, passed=True, valid=True)
    s = worklog.summary("H001")
    assert s["id"] == "H001" and s["n_runs"] == 1 and s["min_runs"] == 3
    assert "run again" in s["next"]


def test_active_hypotheses_filters_by_status(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)                     # H001 is approved
    (tmp_path / "hypotheses" / "H099_draft.yaml").write_text(
        'id: H099\ntitle: "Draft idea"\nstatus: draft\nmin_runs: 3\n', encoding="utf-8")
    ids = [s["id"] for s in worklog.active_hypotheses()]
    assert "H001" in ids and "H099" not in ids


def test_active_hypotheses_sorted_most_worked_first(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    (tmp_path / "hypotheses" / "H002_more.yaml").write_text(
        'id: H002\ntitle: "Second"\nstatus: approved\nmin_runs: 3\n', encoding="utf-8")
    worklog.log_run("H002", metrics={"x": 1}, seed=1)   # H002 has a run, H001 has none
    assert worklog.active_hypotheses()[0]["id"] == "H002"
