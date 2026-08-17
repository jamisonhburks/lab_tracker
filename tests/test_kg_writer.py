"""kg_writer — dedup-by-merge and the research_group (A7) independence field.

All hermetic: STORE is redirected into tmp_path so the real curated_kg.jsonl is never touched.
"""
import kg_writer


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(kg_writer, "STORE", tmp_path / "curated_kg.jsonl")


def test_second_source_merges_evidence_into_one_edge(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    kg_writer.add_association("A", "associates", "B", source="PMID:1")
    rec = kg_writer.add_association("A", "associates", "B", source="PMID:2")
    assert len(kg_writer._load()) == 1          # one edge, not two
    assert len(rec["evidence"]) == 2            # evidence accumulated (the whole point of dedup)


def test_dedup_on_canonical_id_across_surface_forms(tmp_path, monkeypatch):
    # Different surface strings that normalize to the same node id must land on ONE edge.
    _isolate(tmp_path, monkeypatch)
    kg_writer.add_association("ulcerative colitis (UC)", "associates", "IL23R", source="PMID:1",
                              subject_id="Disease:DOID:8577", object_id="Gene:149233")
    kg_writer.add_association("UC", "associates", "IL23R", source="PMID:2",
                              subject_id="Disease:DOID:8577", object_id="Gene:149233")
    assert len(kg_writer._load()) == 1


def test_research_group_persisted_and_roundtrips(tmp_path, monkeypatch):
    # A7: the independence signal must survive the write AND be rebuilt by to_association,
    # so a future confidence scorer can discount correlated (same-group) sources.
    _isolate(tmp_path, monkeypatch)
    rec = kg_writer.add_association("A", "associates", "B", source="PMID:1", research_group="Smith")
    assert rec["evidence"][0]["research_group"] == "Smith"
    assoc = kg_writer.to_association(rec)
    assert assoc.evidence[0].research_group == "Smith"


def test_legacy_record_without_research_group_still_lifts(tmp_path, monkeypatch):
    # Records written before A7 have no research_group key — to_association must not choke.
    _isolate(tmp_path, monkeypatch)
    legacy = {"subject": "A", "subject_id": None, "predicate": "associates",
              "object": "B", "object_id": None, "epistemic_type": "empirical",
              "evidence": [{"source": "PMID:9", "direction": "supports"}]}
    assoc = kg_writer.to_association(legacy)
    assert assoc.evidence[0].research_group is None


# ---- A5: internal grounding from the lab's own curated KG (length-2 paths) ----------------- #
def test_internally_grounded_via_length2_path(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    kg_writer.add_association("A", "associates", "X", source="PMID:1")
    kg_writer.add_association("X", "associates", "B", source="PMID:2")
    assert kg_writer.internally_grounded("A", "B") is True      # A—X—B
    assert kg_writer.internally_grounded("A", "Z") is False     # Z is not in the graph


def test_internally_grounded_excludes_the_direct_edge(tmp_path, monkeypatch):
    # Only the direct A—B edge exists: no intermediate, so it must NOT self-ground (no double count).
    _isolate(tmp_path, monkeypatch)
    kg_writer.add_association("A", "associates", "B", source="PMID:1")
    assert kg_writer.internally_grounded("A", "B") is False


def test_internally_grounded_uses_canonical_ids(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    kg_writer.add_association("alpha", "associates", "mid", source="PMID:1",
                              subject_id="D:1", object_id="D:9")
    kg_writer.add_association("mid", "associates", "beta", source="PMID:2",
                              subject_id="D:9", object_id="D:2")
    assert kg_writer.internally_grounded("alpha", "beta", "D:1", "D:2") is True
