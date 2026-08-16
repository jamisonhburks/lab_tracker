"""lab_retro — the lab-workflow retrospective / coach.

Hermetic: worklog's HYP/EXP are redirected into tmp_path, and the external signal sources
(deadends, calibration, coverage, subscriptions) are monkeypatched to controlled values, so the
retro is tested against a known scenario without touching the repo's real substrate.
"""
import lab_retro


def _isolate(tmp_path, monkeypatch):
    import worklog
    monkeypatch.setattr(worklog, "EXP", tmp_path / "experiments")
    monkeypatch.setattr(worklog, "HYP", tmp_path / "hypotheses")
    (tmp_path / "hypotheses").mkdir()

    def _hyp(hid, status="running", min_runs=3):
        (tmp_path / "hypotheses" / f"{hid}_demo.yaml").write_text(
            f'id: {hid}\ntitle: "Demo {hid}"\nsuccess_metric: "auc>=0.8"\n'
            f"min_runs: {min_runs}\nstatus: {status}\n", encoding="utf-8")

    _hyp("H010")   # will be BURNING — many runs, no passes
    _hyp("H011")   # will be CLEARED — enough passing runs

    for _ in range(6):
        worklog.log_run("H010", metrics={"auc": 0.6}, passed=False, valid=True, contributor="alice")
    for _ in range(3):
        worklog.log_run("H011", metrics={"auc": 0.85}, passed=True, valid=True, contributor="bob")

    # external signals — deterministic stand-ins
    import deadends, calibration, coverage, subscriptions
    monkeypatch.setattr(subscriptions, "known_members", lambda: ["alice", "bob"])
    monkeypatch.setattr(deadends, "all_dead_ends", lambda: [])
    monkeypatch.setattr(calibration, "audit",
                        lambda lens="all": {"n": 12, "ece": 0.05, "net_bias": 0.20,
                                            "bins": [], "brier": 0.2,
                                            "n_adjudicated": 12, "n_stability": 0})
    monkeypatch.setattr(coverage, "compute",
                        lambda member=None, profile_id=None, deep=False: {
                            "adoptable": [("OCT", "classification", [], "")], "frontier": []})

    # retro's own paths → empty tmp dirs (no reports, no sessions, no contribution logs)
    monkeypatch.setattr(lab_retro, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(lab_retro, "SESSIONS", tmp_path / "sessions")
    monkeypatch.setattr(lab_retro, "CONTRIB", tmp_path / "contrib.jsonl")
    monkeypatch.setattr(lab_retro, "MISC", tmp_path / "misc.jsonl")


def test_signals_flag_burning_cleared_calibration_coverage(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    sig = lab_retro.signals()

    by_id = {h["id"]: h for h in sig["hypotheses"]}
    assert by_id["H010"]["burning"] is True and by_id["H010"]["n_pass"] == 0
    assert by_id["H011"]["cleared"] is True and by_id["H011"]["n_pass"] == 3

    assert sig["calibration"]["meaningful"] is True
    assert sig["calibration"]["net_bias"] == 0.20            # over-confident
    assert sig["coverage"]["adoptable"] == 1


def test_render_lab_view_is_coaching_not_ranking(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    out = lab_retro.render()

    # the three coaching sections are present
    assert "WORKING" in out and "NEEDS ATTENTION" in out and "OPTIMIZE" in out
    # the real signals surface
    assert "Burning seeds" in out and "H010" in out
    assert "OVER-confident" in out
    assert "ADOPTABLE" in out
    # cleared-but-unwritten finding shows up as an optimize win
    assert "H011" in out
    # coaching framing, de-identified: the lab view must not expose the run author as blame
    assert "aggregated" in out
    assert "alice" not in out


def test_member_view_is_private_and_scoped(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    out = lab_retro.render(member="alice")
    assert "private coaching for alice" in out
    # alice ran the burning hypothesis; bob's cleared one should not appear in her view
    assert "H010" in out and "H011" not in out


def test_member_view_shows_own_attributed_calibration(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    import calibration
    monkeypatch.setattr(calibration, "audit_member",
                        lambda who, lens="all": {"who": who, "n": 10, "ece": 0.05,
                                                 "net_bias": 0.25, "meaningful": True})
    out = lab_retro.render(member="alice")
    # the member sees THEIR OWN lean, phrased as such (not "the lab")
    assert "Your calls are systematically OVER-confident" in out
    assert "your own outcomes" in out


def test_lab_view_aggregates_member_leans_without_naming(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    import calibration
    monkeypatch.setattr(calibration, "audit_by_member",
                        lambda lens="all": {
                            "alice": {"who": "alice", "n": 10, "net_bias": 0.20,
                                      "meaningful": True, "ece": 0.1, "bins": []},
                            "bob": {"who": "bob", "n": 9, "net_bias": -0.16,
                                    "meaningful": True, "ece": 0.1, "bins": []}})
    out = lab_retro.render()
    assert "2 member(s) show a calibration lean" in out
    assert "alice" not in out and "bob" not in out      # de-identified by design


def test_retro_lines_preview_nonempty(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    lines = lab_retro.retro_lines()
    assert lines and any("Burning seeds" in l for l in lines)
