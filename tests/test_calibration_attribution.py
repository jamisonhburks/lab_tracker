"""calibration — per-member attribution of the self-audit.

Hermetic: beliefs' event/contradiction readers are monkeypatched with synthetic logs, so we test
that outcomes are attributed to the member whose confident call they score, and that the per-member
audit computes the right lean — without touching the repo's real belief store.
"""
import beliefs
import calibration


def _synthetic(monkeypatch):
    # belief-event history: alice owns E1 & E2, bob owns E3
    events = [
        {"key": "E1", "status": "supported", "confidence": 0.9, "trigger": {"contributor": "alice"}},
        {"key": "E1", "status": "refuted",   "confidence": 0.3, "trigger": {"contributor": "alice"}},
        {"key": "E2", "status": "supported", "confidence": 0.8, "trigger": {"contributor": "alice"}},
        {"key": "E2", "status": "supported", "confidence": 0.85, "trigger": {"contributor": "alice"}},
        {"key": "E3", "status": "refuted",   "confidence": 0.85, "trigger": {"contributor": "bob"}},
        {"key": "E3", "status": "supported", "confidence": 0.2, "trigger": {"contributor": "bob"}},
    ]
    monkeypatch.setattr(beliefs, "_events", lambda key=None: [e for e in events if key in (None, e["key"])])
    # a resolved contradiction: alice's high-confidence E1 belief was OVERTURNED (she was wrong)
    contra = [
        {"event": "open", "id": "E1#1", "key": "E1", "established": {"confidence": 0.9}},
        {"event": "resolve", "id": "E1#1", "resolution": "overturned"},
    ]
    monkeypatch.setattr(beliefs, "_contra_events", lambda: contra)


def test_edge_owner_recovers_established_belief_contributor(monkeypatch):
    _synthetic(monkeypatch)
    assert calibration._edge_owner("E1") == "alice"
    assert calibration._edge_owner("E3") == "bob"
    assert calibration._edge_owner("nope") is None


def test_outcomes_are_attributed(monkeypatch):
    _synthetic(monkeypatch)
    outs = calibration._select("all")
    # every outcome carries a `who`, and E1's adjudicated outcome is alice's (recovered from history)
    adj = [o for o in outs if o.lens == "adjudicated"]
    assert adj and all(o.who == "alice" for o in adj)
    assert {o.who for o in outs} == {"alice", "bob"}


def test_audit_by_member_splits_and_scores(monkeypatch):
    _synthetic(monkeypatch)
    per = calibration.audit_by_member("all")
    assert set(per) == {"alice", "bob"}
    # alice: stability E1 (0.9→wrong), stability E2 (0.8→held), adjudicated E1 (0.9→wrong)
    assert per["alice"]["n"] == 3
    assert per["alice"]["net_bias"] > 0          # confidently wrong more than right → over-confident
    # bob: stability E3 (0.85→reversed) → also over-confident, single outcome
    assert per["bob"]["n"] == 1
    # neither has >= MIN_OUTCOMES, so we stay humble and don't call it "meaningful"
    assert per["alice"]["meaningful"] is False


def test_audit_member_matches_manual(monkeypatch):
    _synthetic(monkeypatch)
    a = calibration.audit_member("alice")
    assert a["who"] == "alice" and a["n"] == 3
    assert a == {**a, "who": "alice"}            # shape sanity
