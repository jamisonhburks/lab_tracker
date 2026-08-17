"""tickets — the alpha issue tracker: file, list/filter/order, triage, stats. Hermetic: the store
is redirected into tmp_path.
"""
import pytest

import tickets


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setattr(tickets, "TICKETS", tmp_path / "tickets.jsonl")


def test_file_assigns_sequential_ids_and_attributes():
    a = tickets.file_ticket("KG load fails", body="stack trace…", severity="high",
                            area="kg", reporter="alice")
    b = tickets.file_ticket("onboarding loops", reporter="bob")
    assert a == "T-0001" and b == "T-0002"
    t = tickets.list_tickets()[0]
    assert t["reporter"] in ("alice", "bob") and t["status"] == "open"
    # a bad severity is normalized, not rejected
    c = tickets.file_ticket("typo", severity="catastrophic", reporter="alice")
    assert tickets.update_ticket(c) is not None
    assert next(x for x in tickets.list_tickets() if x["id"] == c)["severity"] == "medium"


def test_ordering_open_then_severity():
    tickets.file_ticket("low open", severity="low", reporter="a")        # T-0001
    tickets.file_ticket("blocker open", severity="blocker", reporter="a")  # T-0002
    closed = tickets.file_ticket("high", severity="high", reporter="a")   # T-0003
    tickets.update_ticket(closed, status="closed", note="fixed")
    order = [t["id"] for t in tickets.list_tickets()]
    # open before closed; within open, blocker before low
    assert order == ["T-0002", "T-0001", "T-0003"]


def test_update_status_note_and_resolution():
    tid = tickets.file_ticket("mcp not connecting", reporter="carol")
    assert tickets.update_ticket(tid, status="ack", by="admin")["status"] == "ack"
    t = tickets.update_ticket(tid, status="closed", note="was a stale token", by="admin")
    assert t["status"] == "closed" and t["resolution"] == "was a stale token"
    # history records the trail
    actions = [h["action"] for h in t["history"]]
    assert actions == ["filed", "ack", "closed"]
    assert tickets.update_ticket("T-9999", status="ack") is None      # unknown id → None


def test_filters_and_stats():
    tickets.file_ticket("a", area="kg", reporter="alice")
    tickets.file_ticket("b", area="onboarding", reporter="bob")
    done = tickets.file_ticket("c", area="kg", reporter="alice")
    tickets.update_ticket(done, status="closed")
    assert [t["id"] for t in tickets.list_tickets(area="kg")] == ["T-0001", "T-0003"]
    assert [t["id"] for t in tickets.list_tickets(reporter="bob")] == ["T-0002"]
    assert [t["id"] for t in tickets.list_tickets(status="open")] == ["T-0001", "T-0002"]
    s = tickets.stats()
    assert s["total"] == 3 and s["open"] == 2 and s["by_status"]["closed"] == 1


def test_render_and_empty():
    assert "No tickets" in tickets.render()
    tickets.file_ticket("something broke", severity="blocker", area="mcp", reporter="dave")
    out = tickets.render(status="open")
    assert "T-0001" in out and "blocker" in out and "dave" in out


# --------------------------------------------------------------------------- #
# auto_file — unhandled-error tickets, deduplicated, never raising              #
# --------------------------------------------------------------------------- #
def test_auto_file_creates_high_severity_auto_ticket():
    msg = tickets.auto_file(ValueError("boom on line 3"), tool="curate_literature",
                            args={"query": "x"}, area="mcp", reporter="alice")
    assert msg == "filed T-0001"
    t = tickets.list_tickets()[0]
    assert t["severity"] == "high" and t["auto"] is True and t["reporter"] == "alice"
    assert "ValueError" in t["title"] and "curate_literature" in t["body"]


def test_auto_file_dedups_recurring_error_while_open():
    tickets.auto_file(KeyError("k"), tool="query_kg", reporter="bob")
    again = tickets.auto_file(KeyError("k"), tool="query_kg", reporter="bob")
    assert "recurred x2" in again
    assert len(tickets._load()) == 1                       # one ticket, occurrence bumped
    assert tickets.list_tickets()[0]["occurrences"] == 2
    # a DIFFERENT error signature files a fresh ticket
    tickets.auto_file(TypeError("t"), tool="query_kg", reporter="bob")
    assert len(tickets._load()) == 2
    # once closed, the same error files anew (it may have regressed)
    tickets.update_ticket("T-0001", status="closed")
    tickets.auto_file(KeyError("k"), tool="query_kg", reporter="bob")
    assert len(tickets._load()) == 3


def test_auto_file_never_raises(monkeypatch):
    # even if the store write blows up, auto_file must swallow it (don't compound the failure)
    monkeypatch.setattr(tickets, "_save", lambda rows: (_ for _ in ()).throw(OSError("disk full")))
    assert tickets.auto_file(RuntimeError("x"), tool="t") == "(auto-ticket failed)"


def test_auto_file_reporter_falls_back_to_env(monkeypatch):
    monkeypatch.delenv("SUBSTRATE_CONTRIBUTOR", raising=False)
    monkeypatch.setenv("USER", "clusteruser")
    tickets.auto_file(ValueError("x"), tool="t")
    assert tickets.list_tickets()[0]["reporter"] == "clusteruser"
