"""token accounting — meter capture, activity/outcome labels, provisional discovery, audit rollup.

Hermetic: the process-global meter is reset around every test and the durable ledger dir is
redirected into tmp_path, so nothing touches real spend logs.
"""
import json

import pytest

import label_discovery
import token_audit
import token_meter
from token_meter import SpendEvent, SpendMeter


@pytest.fixture(autouse=True)
def _clean_meter():
    token_meter.reset()
    token_meter.unbind()
    yield
    token_meter.reset()
    token_meter.unbind()


# --------------------------------------------------------------------------- #
# vocab + mapping                                                              #
# --------------------------------------------------------------------------- #
def test_tool_activity_mapping_and_resolve():
    assert token_meter.activity_for_tool("search_pubmed") == "lit_search"
    assert token_meter.activity_for_tool("find_paths") == "kg_traversal"
    # known tool -> confident, not provisional
    label, prov, hint = token_meter.resolve_activity("curate_literature")
    assert (label, prov, hint) == ("lit_search", False, "")
    # unknown tool -> provisional with the name kept as a hint (NOT dropped to uncategorized silently)
    label, prov, hint = token_meter.resolve_activity("frobnicate_widgets")
    assert label == "uncategorized" and prov is True and hint == "frobnicate_widgets"


def test_every_mapped_activity_is_in_vocabulary():
    for act in token_meter.TOOL_ACTIVITY.values():
        assert act in token_meter.ACTIVITIES


# --------------------------------------------------------------------------- #
# pricing — local is $0, frontier is priced                                    #
# --------------------------------------------------------------------------- #
def test_pricing_local_free_frontier_paid():
    assert token_meter.price_usd("ollama", "qwen3:14b", 10_000, 10_000) == 0.0
    cost = token_meter.price_usd("anthropic", "claude-opus-4-8", 1_000_000, 1_000_000)
    assert cost == pytest.approx(15.0 + 75.0)
    # model-id suffixes (e.g. [1m], dated) still match the base rate
    assert token_meter.price_usd("anthropic", "claude-opus-4-8[1m]", 1_000_000, 0) == pytest.approx(15.0)
    # unknown model -> not guessed, priced 0
    assert token_meter.price_usd("anthropic", "some-future-model", 1_000_000, 0) == 0.0


# --------------------------------------------------------------------------- #
# capture flows through context                                                #
# --------------------------------------------------------------------------- #
def test_on_llm_call_captures_current_activity_and_outcome():
    with token_meter.activity("lit_search"):
        token_meter.on_llm_call("anthropic", "claude-opus-4-8", 100, 50)
    ev = token_meter.meter().events[-1]
    assert ev.activity == "lit_search" and ev.outcome == "productive"
    assert ev.in_tok == 100 and ev.out_tok == 50 and ev.usd > 0
    assert ev.is_paid


def test_retry_outcome_and_layer_and_provisional_context():
    with token_meter.run(run_id="R1", layer="specialist"):
        with token_meter.activity("uncategorized", provisional=True, hint="run_bash"):
            with token_meter.outcome("retry"):
                token_meter.on_llm_call("anthropic", "claude-opus-4-8", 10, 10)
    ev = token_meter.meter().events[-1]
    assert ev.outcome == "retry" and ev.layer == "specialist"
    assert ev.provisional and ev.hint == "run_bash" and ev.run_id == "R1"


def test_record_external_covers_offband_paid_tokens():
    ev = token_meter.record_external("evidence_assess", "anthropic", "claude-opus-4-8",
                                     2_000, 1_000, layer="external")
    assert ev.layer == "external" and ev.usd > 0
    assert token_meter.meter().events == [ev]


def test_observer_receives_events_but_never_breaks_run():
    seen = []
    token_meter.observe(lambda e: seen.append(e))
    token_meter.observe(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))  # misbehaving observer
    token_meter.on_llm_call("ollama", "qwen3:14b", 5, 5)
    assert len(seen) == 1        # good observer still fired; bad one was swallowed


# --------------------------------------------------------------------------- #
# rollups                                                                       #
# --------------------------------------------------------------------------- #
def test_spendmeter_rollups_and_waste_report():
    m = SpendMeter()
    m.add(SpendEvent("lit_search", "productive", "ollama", "qwen", 100, 100, 0.0))
    m.add(SpendEvent("lit_search", "redundant", "ollama", "qwen", 100, 100, 0.0))
    m.add(SpendEvent("planning", "productive", "anthropic", "claude-opus-4-8", 50, 50, 0.01))
    tot = m.totals()
    assert tot["tok"] == 500 and tot["calls"] == 3     # 200 + 200 + 100
    assert tot["waste_tok"] == 200 and tot["waste_frac"] == pytest.approx(200 / 500)
    wr = m.waste_report()
    assert wr[0]["activity"] == "lit_search"          # worst waste share first
    assert wr[0]["waste_frac"] == pytest.approx(0.5)   # 200 of lit_search's 400 tokens


def test_summary_line_mentions_paid_and_waste():
    with token_meter.activity("lit_search", outcome="redundant"):
        token_meter.on_llm_call("anthropic", "claude-opus-4-8", 1000, 1000)
    line = token_meter.summary_line()
    assert "tokens:" in line and "paid" in line and "waste" in line


# --------------------------------------------------------------------------- #
# flush + audit                                                                 #
# --------------------------------------------------------------------------- #
def test_flush_writes_jsonl_and_audit_reads_it(tmp_path, monkeypatch):
    monkeypatch.setattr(token_meter, "LEDGER_DIR", tmp_path)
    monkeypatch.setattr(token_audit, "LEDGER_DIR", tmp_path)
    with token_meter.run(run_id="R2"):
        with token_meter.activity("kg_traversal"):
            token_meter.on_llm_call("anthropic", "claude-opus-4-8", 300, 200)
        with token_meter.activity("kg_traversal", outcome="redundant"):
            token_meter.on_llm_call("ollama", "qwen3:14b", 300, 200)
    p = token_meter.flush()
    assert p is not None and p.exists()
    lines = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    assert len(lines) == 2
    # a second flush with no new events writes nothing
    assert token_meter.flush() is None

    events = token_audit.load_events()
    assert len(events) == 2
    rep = token_audit.report(events)
    assert "Token audit" in rep and "kg_traversal" in rep
    # paid-only filter keeps just the anthropic call
    assert len(token_audit.load_events(paid_only=True)) == 1


# --------------------------------------------------------------------------- #
# emergent-label discovery                                                      #
# --------------------------------------------------------------------------- #
def test_discovery_clusters_provisional_hints_across_sources():
    events = [
        {"provisional": True, "hint": "run_bash_script", "in_tok": 100, "out_tok": 100, "run_id": "a"},
        {"provisional": True, "hint": "run_bash_command", "in_tok": 100, "out_tok": 100, "run_id": "b"},
        {"provisional": True, "hint": "plot_figure_seaborn", "in_tok": 50, "out_tok": 50, "run_id": "a"},
        {"provisional": False, "hint": "", "activity": "lit_search", "in_tok": 999, "out_tok": 0},
    ]
    cands = label_discovery.discover(events, min_support=2)
    # the two 'run_bash_*' hints cluster; the singleton 'plot_*' is dropped by min_support
    assert len(cands) == 1
    c = cands[0]
    assert set(c["hints"]) == {"run_bash_script", "run_bash_command"}
    assert c["events"] == 2 and c["sources"] == 2       # seen across two distinct runs/users
    assert "bash" in c["suggested_label"]


def test_discovery_ignores_confidently_labelled_spend():
    events = [{"provisional": False, "hint": "", "activity": "lit_search",
               "in_tok": 10, "out_tok": 10}]
    assert label_discovery.discover(events) == []
