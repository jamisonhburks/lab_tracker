"""pending — owner-scoped unfinished work across the tiers (conform → WIP → consensus).
Hermetic: registry/pending/substrate-root → tmp_path.
"""
import pending
import projects


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "REGISTRY", tmp_path / "reg.jsonl")
    monkeypatch.setattr(projects, "PENDING", tmp_path / "pending.jsonl")
    monkeypatch.setattr(pending, "ROOT", tmp_path / "substrate")     # empty → root adds nothing
    (tmp_path / "substrate" / "hypotheses").mkdir(parents=True)


def _proj(tmp_path, name, hyps):
    p = tmp_path / name
    (p / "hypotheses").mkdir(parents=True)
    (p / "reports").mkdir(parents=True)
    for hid, evaluated in hyps:
        (p / "hypotheses" / f"{hid}_x.yaml").write_text(
            f"id: {hid}\ntitle: About {hid}\nstatus: complete\n", encoding="utf-8")
        if evaluated:
            (p / "reports" / f"{hid}_evaluation.md").write_text("verdict", encoding="utf-8")
    return p


def test_splits_unevaluated_vs_unpromoted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _proj(tmp_path, "PathTIGR", [("H001", False), ("H002", True)])
    projects.register_project(str(p), by="jamison.burks")
    u = pending.unfinished("jamison.burks")
    assert [h["id"] for h in u["unevaluated"]] == ["H001"]       # no report → not evaluated
    assert [h["id"] for h in u["unpromoted"]] == ["H002"]        # has report → promotion candidate
    assert u["unregistered"] == [] and u["projects"] == ["PathTIGR"]


def test_conformed_but_unregistered_surfaces_then_clears(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _proj(tmp_path, "NewProj", [("H001", False)])
    projects.record_conformed(str(p))                            # conformed, NOT registered
    u = pending.unfinished("jamison.burks")
    assert len(u["unregistered"]) == 1 and u["unregistered"][0]["path"].endswith("NewProj")
    projects.register_project(str(p), by="jamison.burks")        # register → drops off
    assert pending.unfinished("jamison.burks")["unregistered"] == []


def test_owner_scoped(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    projects.register_project(str(_proj(tmp_path, "Other", [("H001", False)])), by="someone.else")
    u = pending.unfinished("jamison.burks")
    assert u["unevaluated"] == [] and u["projects"] == []        # not my project


def test_summary_line_and_render(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    projects.register_project(str(_proj(tmp_path, "PathTIGR", [("H001", False), ("H002", True)])),
                              by="jamison.burks")
    line = pending.summary_line("jamison.burks")
    assert "not yet evaluated" in line and "not yet contributed" in line
    r = pending.render("jamison.burks")
    assert "H001" in r and "reports/H001_evaluation.md" in r and "contribute_finding" in r


def test_nothing_pending(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert "nothing pending" in pending.render("jamison.burks")
    assert pending.summary_line("jamison.burks") == ""
