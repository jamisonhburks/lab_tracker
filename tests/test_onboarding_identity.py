"""P0a — the roster is keyed on the member's IDENTITY, not the typed display name, so
onboarding_status actually flips to ✓ (the bug the alpha transcript missed). Hermetic: PROFILES → tmp.
"""
import threading

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


def test_onboarding_status_flips_when_added_by_identity(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("SUBSTRATE_CONTRIBUTOR", "jamison.burks")
    assert onboarding.status()["in_roster"] is False            # before
    # the MCP tool passes the caller identity as member_id (here: the env identity, as in solo mode)
    lab_profile.add_member("Jamie Burks", member_id=lab_profile._identity())
    assert onboarding.status()["in_roster"] is True             # the ✓ the transcript never got


def test_direct_add_keys_on_name_for_admin_adds_other(tmp_path, monkeypatch):
    pid = _isolate(tmp_path, monkeypatch)
    # a direct call with no member_id (admin registering a colleague) keys on the given name
    lab_profile.add_member("priya")
    assert lab_profile.roster(pid) == ["priya"]


def test_add_member_idempotent_and_updates_alias(tmp_path, monkeypatch):
    pid = _isolate(tmp_path, monkeypatch)
    lab_profile.add_member("Jamie", member_id="jamison.burks")
    again = lab_profile.add_member("Jamison Burks", member_id="jamison.burks")
    assert "already on" in again
    assert lab_profile.roster(pid) == ["jamison.burks"]          # not duplicated
    assert lab_profile.display_name("jamison.burks", pid) == "Jamison Burks"   # alias refreshed


def test_concurrent_add_member_loses_nobody(tmp_path, monkeypatch):
    # multiple sessions onboarding at once must not drop a member (the store_lock'd roster write)
    pid = _isolate(tmp_path, monkeypatch)
    ids = [f"m{i:02d}" for i in range(24)]
    threads = [threading.Thread(target=lambda n=n: lab_profile.add_member(n, member_id=n)) for n in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(lab_profile.roster(pid)) == sorted(ids)        # all 24 landed, none lost
