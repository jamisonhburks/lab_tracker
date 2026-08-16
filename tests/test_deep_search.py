"""deep_search — the distillation ingestion path: junk filter (B4), normalization (B1),
independence signal (A7). Hermetic: kg_writer, the KG normalizer, PMID metadata, and the
topic cache are all stubbed, so no network and no KG load.
"""
import deep_search


def _stub_write(monkeypatch):
    """Capture add_association calls; neutralize normalization, metadata, and the cache."""
    calls = []
    monkeypatch.setattr(deep_search.kg_writer, "add_association",
                        lambda *a, **k: calls.append({"args": a, "kw": k}) or {})
    monkeypatch.setattr(deep_search, "_normalize", lambda name: None)
    monkeypatch.setattr(deep_search, "_resolve_meta", lambda pmids: {})
    monkeypatch.setattr(deep_search, "_append_cache", lambda *a, **k: None)
    return calls


# ---- B4: the junk/structural guard must always run --------------------------------------- #
def test_ok_rejects_junk_and_missing_source():
    assert deep_search._ok({"subject": "metformin", "predicate": "treats",
                            "object": "type 2 diabetes", "source": "PMID:1"})
    assert not deep_search._ok({"subject": "GSE12345", "predicate": "p",
                                "object": "B", "source": "PMID:1"})      # bare accession
    assert not deep_search._ok({"subject": "A", "predicate": "p",
                                "object": "9999", "source": "PMID:1"})   # bare number
    assert not deep_search._ok({"subject": "A", "predicate": "p",
                                "object": "B", "source": ""})            # no provenance


def test_accept_verdict_no_longer_bypasses_junk_filter(monkeypatch):
    calls = _stub_write(monkeypatch)
    junk = [{"subject": "GSE12345", "predicate": "p", "object": "9999", "source": "PMID:1"}]
    msg = deep_search.record_distillation("t", junk, rigor_verdict="accept")
    assert calls == []                       # malformed row NOT written, even on 'accept'
    assert "skipped" in msg


def test_reject_verdict_drops_the_batch(monkeypatch):
    calls = _stub_write(monkeypatch)
    good = [{"subject": "metformin", "predicate": "treats",
             "object": "type 2 diabetes", "source": "PMID:1"}]
    deep_search.record_distillation("t", good, rigor_verdict="reject")
    assert calls == []                       # 'reject' can only tighten → nothing written


def test_valid_rows_are_written(monkeypatch):
    calls = _stub_write(monkeypatch)
    good = [{"subject": "metformin", "predicate": "treats",
             "object": "type 2 diabetes", "source": "PMID:1"}]
    deep_search.record_distillation("t", good)
    assert len(calls) == 1


# ---- B1 + A7: distillation normalizes entities and stores the independence signal --------- #
def test_distillation_normalizes_and_records_research_group(monkeypatch):
    calls = _stub_write(monkeypatch)
    # 'T2DM' resolves to a canonical node; last-author resolves to a group.
    monkeypatch.setattr(deep_search, "_normalize",
                        lambda name: {"id": "Disease:DOID:9352", "name": "type 2 diabetes"}
                        if name.lower() in ("t2dm", "type 2 diabetes") else None)
    monkeypatch.setattr(deep_search, "_resolve_meta", lambda pmids: {"1": {"last_author": "Smith"}})
    assoc = [{"subject": "T2DM", "predicate": "treated_by", "object": "metformin", "source": "PMID:1"}]
    deep_search.record_distillation("t", assoc)

    assert len(calls) == 1
    args, kw = calls[0]["args"], calls[0]["kw"]
    assert args[0] == "type 2 diabetes"                  # B1: subject normalized off the raw 'T2DM'
    assert kw["subject_id"] == "Disease:DOID:9352"       # B1: canonical id passed for dedup
    assert kw["research_group"] == "Smith"               # A7: independence signal captured at write


def test_distillation_keeps_raw_string_on_normalization_miss(monkeypatch):
    calls = _stub_write(monkeypatch)   # _normalize -> None (miss)
    assoc = [{"subject": "NovelEntity", "predicate": "associates",
              "object": "OtherEntity", "source": "PMID:1"}]
    deep_search.record_distillation("t", assoc)
    args, kw = calls[0]["args"], calls[0]["kw"]
    assert args[0] == "NovelEntity"          # unresolved entities are kept, not dropped
    assert kw["subject_id"] is None
