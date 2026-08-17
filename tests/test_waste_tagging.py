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


def _stub_curate(monkeypatch, covered: bool, tmp_path):
    import agent
    monkeypatch.setattr(agent.biblio, "STORE", tmp_path / "works.jsonl")   # keep biblio hermetic
    status = "ALREADY DEEP-SEARCHED: metformin (COVERED)" if covered else "fresh topic"
    monkeypatch.setattr(agent.deep_search, "search_status", lambda q: status)
    monkeypatch.setattr(agent, "_fetch_articles",
                        lambda q, n: [{"pmid": "1", "abstract": "Metformin treats T2D.",
                                       "last_author": "Smith"}])
    monkeypatch.setattr(agent.deep_search, "mark_searched", lambda *a, **k: None)
    monkeypatch.setattr(agent.kg, "normalize_entity", lambda name: None)
    monkeypatch.setattr(agent.kg_writer, "add_association", lambda *a, **k: {})

    def fake_parse(messages, schema, model_cls, **kw):
        token_meter.on_llm_call("ollama", "qwen3:14b", 120, 60)   # simulate the real adapter capture
        return _Result()
    monkeypatch.setattr(agent.llm, "parse", fake_parse)
    return agent


def test_curate_tags_redundant_when_already_covered(monkeypatch, tmp_path):
    agent = _stub_curate(monkeypatch, covered=True, tmp_path=tmp_path)
    with token_meter.activity("lit_search"):            # as the agent dispatch would set it
        agent.curate_literature("metformin type 2 diabetes")
    evs = token_meter.meter().events
    assert evs and all(e.outcome == "redundant" for e in evs)
    assert all(e.activity == "lit_search" for e in evs)


def test_curate_is_productive_when_topic_is_fresh(monkeypatch, tmp_path):
    agent = _stub_curate(monkeypatch, covered=False, tmp_path=tmp_path)
    with token_meter.activity("lit_search"):
        agent.curate_literature("brand new topic")
    evs = token_meter.meter().events
    assert evs and all(e.outcome == "productive" for e in evs)
