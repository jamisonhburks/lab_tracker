"""P0a — the roster is keyed on the member's IDENTITY, not the typed display name, so
onboarding_status actually flips to ✓ (the bug the alpha transcript missed). Hermetic: PROFILES → tmp.
"""
import lab_profile
import onboarding


def _isolate(tmp_path, monkeypatch, pid="testlab"):
    monkeypatch.setattr(lab_profile, "PROFILES", tmp_path)
    monkeypatch.setattr(lab_profile, "_default_id", lambda: pid)
    (tmp_path / f"{pid}.yaml").write_text("name: Test Lab\nmembers: []\n", encoding="utf-8")
    return pid


def test_add_member_keys_on_identity_keeps_name_as_alias(tmp_path, monkeypatch):
    pid = _isolate(tmp_path, monkeypatch)
    out = lab_profile.add_member("Jamie Burks", member_id="jamison.burks")
    assert "Jamie Burks" in out
    assert lab_profile.roster(pid) == ["jamison.burks"]          # identity, NOT the display name
    assert lab_profile.display_name("jamison.burks", pid) == "Jamie Burks"


def test_onboarding_status_flips_to_in_roster(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("SUBSTRATE_CONTRIBUTOR", "jamison.burks")
    assert onboarding.status()["in_roster"] is False            # before
    lab_profile.add_member("Jamie Burks")                        # member_id=None → identity (env)
    assert onboarding.status()["in_roster"] is True             # the ✓ the transcript never got


def test_add_member_idempotent_and_updates_alias(tmp_path, monkeypatch):
    pid = _isolate(tmp_path, monkeypatch)
    lab_profile.add_member("Jamie", member_id="jamison.burks")
    again = lab_profile.add_member("Jamison Burks", member_id="jamison.burks")
    assert "already on" in again
    assert lab_profile.roster(pid) == ["jamison.burks"]          # not duplicated
    assert lab_profile.display_name("jamison.burks", pid) == "Jamison Burks"   # alias refreshed


def test_add_member_falls_back_to_env_identity(tmp_path, monkeypatch):
    pid = _isolate(tmp_path, monkeypatch)
    monkeypatch.delenv("SUBSTRATE_CONTRIBUTOR", raising=False)
    monkeypatch.setenv("USER", "clusteruser")
    lab_profile.add_member("Display Only")                       # no member_id → $USER
    assert lab_profile.roster(pid) == ["clusteruser"]
