"""onboarding — first-session intake STATE + the roster add. Hermetic (every source stubbed)."""
import deep_search
import lab_profile
import onboarding
import subscriptions
import worklog


def _stub(monkeypatch, roster=(), pubs=(), follows=(), topics=()):
    monkeypatch.setattr(lab_profile, "roster", lambda profile_id=None: list(roster))
    monkeypatch.setattr(lab_profile, "publications", lambda member=None, profile_id=None: list(pubs))
    monkeypatch.setattr(subscriptions, "subscriptions_of", lambda who: list(follows))
    monkeypatch.setattr(worklog, "active_hypotheses", lambda *a, **k: [])
    monkeypatch.setattr(deep_search, "_cache",
                        lambda: [{"topic": t, "contributor": "alice"} for t in topics])


def test_status_all_missing_points_at_roster(monkeypatch):
    _stub(monkeypatch)
    s = onboarding.status("newbie")
    assert s["in_roster"] is False and s["complete"] is False
    assert "roster" in s["next"]


def test_next_step_progresses_as_items_fill(monkeypatch):
    _stub(monkeypatch, roster=["alice"])
    assert "papers" in onboarding.status("alice")["next"]
    _stub(monkeypatch, roster=["alice"], pubs=[{"title": "x"}])
    assert "follow" in onboarding.status("alice")["next"]


def test_complete_on_the_three_basics(monkeypatch):
    _stub(monkeypatch, roster=["alice"], pubs=[{"title": "x"}], follows=[("member", "bob")])
    assert onboarding.status("alice")["complete"] is True


def test_render_stays_short_and_glanceable(monkeypatch):
    _stub(monkeypatch, roster=["alice"])
    out = onboarding.render("alice")
    assert out.count("\n") <= 6                 # compact by design (anti-overwhelm)
    assert "○" in out and "→ next:" in out


def test_add_member_idempotent_and_preserves_comments(tmp_path, monkeypatch):
    prof = tmp_path / "profiles"
    prof.mkdir()
    (prof / "demo.yaml").write_text(
        "# a comment line\nid: demo\nname: Demo\nmembers: [jamison]\nfocus: stuff\n", encoding="utf-8")
    monkeypatch.setattr(lab_profile, "PROFILES", prof)
    monkeypatch.setenv("SUBSTRATE_LAB", "demo")

    assert "added priya" in lab_profile.add_member("priya").lower()
    assert lab_profile.roster("demo") == ["jamison", "priya"]
    assert "# a comment line" in (prof / "demo.yaml").read_text()      # comments preserved
    assert "already" in lab_profile.add_member("priya").lower()        # idempotent
