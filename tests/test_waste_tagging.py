"""waste tagging — novelty→redundant and deadends→dead_end are wired into the token audit.

Verifies the two auto-detected waste outcomes beyond `retry`:
  - curate_literature tags its per-paper extraction `redundant` when the topic was already covered;
  - an outer `dead_end` tag (set by refine_hypothesis for an evidenced dead end) is never downgraded
    to `redundant` by the inner curate guard.
"""
import pytest

import token_meter


@pytest.fixture(autouse=True)
def _clean_meter():
    token_meter.reset()
    yield
    token_meter.reset()


# --------------------------------------------------------------------------- #
# outcome precedence — the guard that makes nesting safe                        #
# --------------------------------------------------------------------------- #
def test_current_outcome_reflects_context():
    assert token_meter.current_outcome() == "productive"
    with token_meter.outcome("redundant"):
        assert token_meter.current_outcome() == "redundant"
    assert token_meter.current_outcome() == "productive"


def test_dead_end_is_not_downgraded_to_redundant():
    # mimic refine_hypothesis wrapping curate in dead_end, then curate's redundant guard
    with token_meter.activity("kg_traversal"):
        with token_meter.outcome("dead_end"):
            would_relabel = token_meter.current_outcome() == "productive"   # curate's guard
            assert would_relabel is False                                    # so it stays dead_end
            token_meter.on_llm_call("ollama", "qwen3:14b", 10, 10)
    assert token_meter.meter().events[-1].outcome == "dead_end"


# --------------------------------------------------------------------------- #
# curate_literature → redundant when the lab already covered the topic          #
# --------------------------------------------------------------------------- #
class _Assoc:
    def model_dump(self):
        return {"subject": "metformin", "predicate": "treats", "object": "t2d",
                "direction": "supports"}


class _Result:
    associations = [_Assoc()]


def _stub_curate(monkeypatch, covered: bool, tmp_path, articles=None):
    import agent
    monkeypatch.setattr(agent.biblio, "STORE", tmp_path / "works.jsonl")   # keep biblio hermetic
    monkeypatch.setattr(agent.biblio, "resolve_europepmc", lambda **k: None)  # no network in tests
    status = "ALREADY DEEP-SEARCHED: metformin (COVERED)" if covered else "fresh topic"
    monkeypatch.setattr(agent.deep_search, "search_status", lambda q: status)
    arts = articles or [{"pmid": "1", "abstract": "Metformin treats T2D.", "last_author": "Smith"}]
    monkeypatch.setattr(agent, "_fetch_articles", lambda q, n: arts)
    monkeypatch.setattr(agent.deep_search, "mark_searched", lambda *a, **k: None)
    monkeypatch.setattr(agent.kg, "normalize_entity", lambda name: None)
    monkeypatch.setattr(agent.kg_writer, "add_association", lambda *a, **k: {})

    calls = []

    def fake_parse(messages, schema, model_cls, **kw):
        calls.append(1)
        token_meter.on_llm_call("ollama", "qwen3:14b", 120, 60)   # simulate the real adapter capture
        return _Result()
    monkeypatch.setattr(agent.llm, "parse", fake_parse)
    return agent, calls


def test_curate_tags_redundant_when_already_covered(monkeypatch, tmp_path):
    agent, _ = _stub_curate(monkeypatch, covered=True, tmp_path=tmp_path)
    with token_meter.activity("lit_search"):            # as the agent dispatch would set it
        agent.curate_literature("metformin type 2 diabetes")
    evs = token_meter.meter().events
    assert evs and all(e.outcome == "redundant" for e in evs)
    assert all(e.activity == "lit_search" for e in evs)


def test_curate_is_productive_when_topic_is_fresh(monkeypatch, tmp_path):
    agent, _ = _stub_curate(monkeypatch, covered=False, tmp_path=tmp_path)
    with token_meter.activity("lit_search"):
        agent.curate_literature("brand new topic")
    evs = token_meter.meter().events
    assert evs and all(e.outcome == "productive" for e in evs)


def test_curate_skips_already_ingested_paper(monkeypatch, tmp_path):
    """Paper-level dedup: an already-ingested paper is not re-extracted (no LLM call), but its
    coverage still records the new query; a genuinely new paper is processed."""
    import biblio
    arts = [{"pmid": "1", "abstract": "old paper", "last_author": "X", "title": "A"},
            {"pmid": "2", "abstract": "new paper", "last_author": "Y", "title": "B"}]
    agent, calls = _stub_curate(monkeypatch, covered=False, tmp_path=tmp_path, articles=arts)
    biblio.register({"pmid": "1"}, access="abstract", lab_query="old query")   # prior run ingested #1

    with token_meter.activity("lit_search"):
        agent.curate_literature("new query")

    assert len(calls) == 1                              # only the NEW paper (pmid 2) hit the LLM
    assert {c["lab_query"] for c in biblio.coverage_of("1")} == {"old query", "new query"}
    assert biblio.seen("2")                             # paper 2 now ingested
    # only the new paper's tokens were spent (dedup saved the rest)
    assert len(token_meter.meter().events) == 1


# --------------------------------------------------------------------------- #
# Hook 1: search_pubmed all-known → next planning turn tagged redundant         #
# --------------------------------------------------------------------------- #
def test_search_pubmed_flags_all_known(monkeypatch, tmp_path):
    import agent
    import biblio
    monkeypatch.setattr(biblio, "STORE", tmp_path / "works.jsonl")
    biblio.register({"pmid": "1"}, access="abstract", lab_query="q")   # already ingested
    biblio.register({"pmid": "2"}, access="abstract", lab_query="q")
    monkeypatch.setattr(agent.net, "fetch_bytes",
                        lambda *a, **k: b'{"esearchresult":{"idlist":["1","2"]}}')
    monkeypatch.setattr(agent.net, "fetch_text", lambda *a, **k: "abstracts...")
    out = agent.search_pubmed("q")
    assert agent._REDUNDANT_MARKER in out                # all hits already known → flagged

    # a NEW pmid in the results → not all known → no marker
    monkeypatch.setattr(agent.net, "fetch_bytes",
                        lambda *a, **k: b'{"esearchresult":{"idlist":["1","99"]}}')
    assert agent._REDUNDANT_MARKER not in agent.search_pubmed("q")


# --------------------------------------------------------------------------- #
# Hook 2: campaign abandoned branch → dead_end synthesis                        #
# --------------------------------------------------------------------------- #
class _NextStep:
    def model_dump(self):
        return {"title": "t", "question": "q", "key_change": "k", "rationale": "r"}


def test_synthesize_tags_dead_end_on_abandoned_branch(monkeypatch):
    import campaign
    import llm
    calls = []

    def fake_parse(messages, schema, cls):
        calls.append(1)
        token_meter.on_llm_call("ollama", "qwen3:14b", 100, 50)
        return _NextStep()
    monkeypatch.setattr(llm, "parse", fake_parse)

    campaign._synthesize("Q", "H001", "verdict", "- try a bigger cohort", dead_branch=True)
    assert calls and token_meter.meter().events[-1].outcome == "dead_end"

    token_meter.reset()
    campaign._synthesize("Q", "H001", "verdict", "- try a bigger cohort", dead_branch=False)
    assert token_meter.meter().events[-1].outcome == "productive"


def test_campaign_abandon_marks_node_and_flags_frontier(monkeypatch, tmp_path):
    import campaign
    monkeypatch.setattr(campaign, "CAMP_DIR", tmp_path)
    c = campaign.Campaign("t", "Q")
    c.add("H001", "H001", status="complete")
    c.add("H002", "H002", parent="H001", status="complete")
    assert not c._frontier_abandoned()
    assert c.abandon("H002", "did not pan out")
    assert c.nodes[-1]["status"] == "abandoned" and c._frontier_abandoned()
    assert not c.abandon("H999")                         # unknown id → no-op
