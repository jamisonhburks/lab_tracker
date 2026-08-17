"""P0b — external conformed projects register into the substrate so their work isn't orphaned.
Hermetic: REGISTRY → tmp_path.
"""
import projects


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "REGISTRY", tmp_path / "projects.jsonl")


def _conformed(tmp_path, name="PathTIGR"):
    p = tmp_path / name
    (p / "hypotheses").mkdir(parents=True)
    return p


def test_register_requires_a_conformed_project(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    r = projects.register_project(str(raw))              # no hypotheses/ yet
    assert not r["ok"] and "hypotheses" in r["msg"]
    assert projects.list_projects() == []


def test_missing_dir_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert not projects.register_project(str(tmp_path / "nope"))["ok"]


def test_register_and_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    proj = _conformed(tmp_path)
    r = projects.register_project(str(proj), name="PathTIGR", by="jamison.burks")
    assert r["ok"] and "list_active_work" in r["msg"]
    ps = projects.list_projects()
    assert [p["name"] for p in ps] == ["PathTIGR"] and ps[0]["registered_by"] == "jamison.burks"
    # registering the same path again is a no-op, not a duplicate
    again = projects.register_project(str(proj))
    assert "already registered" in again["msg"]
    assert len(projects.list_projects()) == 1


def test_roots_aggregates_lab_plus_registered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    proj = _conformed(tmp_path, "PathTIGR")
    projects.register_project(str(proj))
    roots = projects.roots(tmp_path / "substrate")
    labels = [lbl for lbl, _ in roots]
    assert labels[0] == "lab"                            # substrate root always first
    assert "PathTIGR" in labels                          # the registered project is aggregated
    # a project whose dir disappears is silently dropped from aggregation
    import shutil
    shutil.rmtree(proj)
    assert [lbl for lbl, _ in projects.roots(tmp_path / "substrate")] == ["lab"]
