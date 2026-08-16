"""Ignition S-tier: roster/member-discovery (subscriptions) + cold-start fallbacks
(briefing, serendipity). All hermetic — roster/profile reads are stubbed, stores go to tmp_path.
"""
import briefing
import lab_profile
import serendipity
import store_lock
import subscriptions


# ---- roster + member discovery ------------------------------------------------------------ #
def _isolate_subs(tmp_path, monkeypatch):
    monkeypatch.setattr(subscriptions, "CONTRIB", tmp_path / "contrib.jsonl")
    monkeypatch.setattr(subscriptions, "MISC", tmp_path / "misc.jsonl")
    monkeypatch.setattr(subscriptions, "SUBS", tmp_path / "subs.jsonl")


def test_known_members_unions_roster_with_contributors(tmp_path, monkeypatch):
    _isolate_subs(tmp_path, monkeypatch)
    monkeypatch.setattr(lab_profile, "roster", lambda profile_id=None: ["alice", "bob", "carol"])
    # 'dave' has attributed work but isn't on the roster — still discoverable
    store_lock.append_jsonl(subscriptions.CONTRIB,
                            {"contributor": "dave", "subject": "A", "predicate": "p",
                             "object": "B", "status": "auto_merged"})
    assert subscriptions.known_members() == ["alice", "bob", "carol", "dave"]


def test_roster_makes_colleagues_followable_before_any_contribution(tmp_path, monkeypatch):
    # The cold-start point: bob is followable on day 1 purely from the roster (no attribution yet).
    _isolate_subs(tmp_path, monkeypatch)
    monkeypatch.setattr(lab_profile, "roster", lambda profile_id=None: ["alice", "bob"])
    assert "bob" in subscriptions.known_members()


def test_list_members_marks_you_and_following(tmp_path, monkeypatch):
    _isolate_subs(tmp_path, monkeypatch)
    monkeypatch.setattr(lab_profile, "roster", lambda profile_id=None: ["alice", "bob"])
    subscriptions.subscribe("alice", "member:bob")
    out = subscriptions.list_members("alice")
    assert "alice  ← you" in out
    assert "bob" in out and "(following)" in out


# ---- briefing cold start ------------------------------------------------------------------ #
def test_briefing_cold_start_orients_from_profile(monkeypatch):
    monkeypatch.setattr(lab_profile, "load", lambda profile_id=None: {"focus": "AI for health\nmore"})
    monkeypatch.setattr(lab_profile, "scope",
                        lambda profile_id=None: {"modalities": ["OCT"], "tasks": ["disentanglement"],
                                                 "paradigms": []})
    monkeypatch.setattr(lab_profile, "covered",
                        lambda profile_id=None, member=None: {"pairs": []})
    lines, step = briefing._cold_start_lines()
    assert any("AI for health" in ln for ln in lines)
    assert any("OCT×disentanglement" in ln for ln in lines)
    assert "assess_idea on OCT×disentanglement" in step


# ---- serendipity cold start --------------------------------------------------------------- #
def test_serendipity_cold_start_surfaces_active_and_frontier(tmp_path, monkeypatch):
    hyp = tmp_path / "hypotheses"
    hyp.mkdir()
    (hyp / "H001_demo.yaml").write_text('id: H001\ntitle: "Latent OCT trajectories"\n')
    monkeypatch.setattr(serendipity, "HYP", hyp)
    monkeypatch.setattr(lab_profile, "scope",
                        lambda profile_id=None: {"modalities": ["OCT"], "tasks": ["survival"],
                                                 "paradigms": []})
    monkeypatch.setattr(lab_profile, "covered",
                        lambda profile_id=None, member=None: {"pairs": []})
    nd = serendipity._cold_start_nudges("newuser")
    keys = [k for k, _ in nd]
    assert any(k.startswith("active:H001") for k in keys)
    assert any(k == "frontier:OCT:survival" for k in keys)
    assert any("Latent OCT trajectories" in t for _, t in nd)


def test_nudges_falls_back_to_cold_start_when_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(serendipity, "_my_entities", lambda who: set())
    monkeypatch.setattr(serendipity, "SEEN", tmp_path / "seen.json")
    monkeypatch.setattr(serendipity, "_cold_start_nudges",
                        lambda who: [("k1", "Nudge one"), ("k2", "Nudge two")])
    assert serendipity.nudges("newuser", max_nudges=2) == ["Nudge one", "Nudge two"]
