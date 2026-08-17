"""biblio — the bibliographic/provenance graph: crosswalk, paper-level dedup, access upgrade,
source→claim links, and a stubbed Europe PMC resolver. Hermetic: STORE is redirected to tmp_path.
"""
import pytest

import biblio


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setattr(biblio, "STORE", tmp_path / "works.jsonl")


# --------------------------------------------------------------------------- #
# id normalization                                                            #
# --------------------------------------------------------------------------- #
def test_id_normalization():
    assert biblio.norm_doi("https://doi.org/10.1/AbC") == "10.1/abc"
    assert biblio.norm_doi("doi: 10.2/x ") == "10.2/x"
    assert biblio.norm_pmid("PMID: 123") == "123"
    assert biblio.norm_pmcid("PMC456") == "PMC456"


# --------------------------------------------------------------------------- #
# register: dedup + crosswalk + access upgrade                                 #
# --------------------------------------------------------------------------- #
def test_register_dedups_and_records_coverage():
    r1 = biblio.register({"pmid": "111"}, title="Paper A", lab_query="metformin t2d")
    assert r1["new"] and r1["key"] == "pmid:111"
    # same paper, second lab query → NOT new, coverage grows (paper-level dedup)
    r2 = biblio.register({"pmid": "111"}, lab_query="metformin AMPK")
    assert not r2["new"]
    cov = biblio.coverage_of("PMID:111")
    assert {c["lab_query"] for c in cov} == {"metformin t2d", "metformin AMPK"}
    # re-registering the SAME query does not duplicate coverage
    biblio.register({"pmid": "111"}, lab_query="metformin t2d")
    assert len(biblio.coverage_of("111")) == 2


def test_crosswalk_merges_when_a_doi_arrives_later():
    biblio.register({"pmid": "222"}, title="Paper B", lab_query="q")
    # a resolver later learns the DOI for the same paper (arrives with both ids)
    r = biblio.register({"pmid": "222", "doi": "10.9/paperb"}, access="abstract")
    assert not r["new"]                                  # merged onto the existing Work, not a new one
    w = biblio.get("10.9/PAPERB")                        # now findable by DOI too
    assert w is not None and "doi:10.9/paperb" in w["xrefs"] and "pmid:222" in w["xrefs"]
    assert len(biblio._load()) == 1                      # still ONE work


def test_access_upgrades_monotonically():
    biblio.register({"pmid": "333"}, access="abstract", lab_query="q")
    assert biblio.access_of("333") == "abstract"
    up = biblio.register({"pmid": "333"}, access="full_text", text_source="europepmc")
    assert up["access_upgraded"] and biblio.access_of("333") == "full_text"
    # a later abstract-only pass must NOT downgrade a full-text Work
    down = biblio.register({"pmid": "333"}, access="abstract")
    assert not down["access_upgraded"] and biblio.access_of("333") == "full_text"


def test_seen_respects_min_access():
    biblio.register({"pmid": "444"}, access="abstract", lab_query="q")
    assert biblio.seen("PMID:444")                        # seen at abstract
    assert biblio.seen("444", min_access="abstract")
    assert not biblio.seen("444", min_access="full_text") # not yet full text
    assert not biblio.seen("999")                         # never registered


# --------------------------------------------------------------------------- #
# source → claim links                                                         #
# --------------------------------------------------------------------------- #
def test_link_association_traces_support():
    biblio.register({"pmid": "555"}, lab_query="q")
    assert biblio.link_association("PMID:555", "metformin|treats|t2d")
    assert biblio.link_association("555", "metformin|treats|t2d")   # idempotent
    w = biblio.get("555")
    assert w["supports"] == ["metformin|treats|t2d"]
    sup = biblio.supporters_of("metformin|treats|t2d")
    assert len(sup) == 1 and sup[0]["key"] == "pmid:555"
    # linking an unknown paper is a no-op, not a crash
    assert biblio.link_association("PMID:000", "x|y|z") is False


def test_register_requires_an_id():
    with pytest.raises(ValueError):
        biblio.register({}, lab_query="q")


def test_stats_summary():
    biblio.register({"pmid": "1"}, access="abstract", lab_query="q")
    biblio.register({"pmid": "2"}, access="full_text", lab_query="q")
    biblio.link_association("1", "a|b|c")
    s = biblio.stats()
    assert s["works"] == 2 and s["by_access"]["full_text"] == 1 and s["links"] == 1


# --------------------------------------------------------------------------- #
# resolver (network stubbed)                                                    #
# --------------------------------------------------------------------------- #
def test_resolve_europepmc_parses_and_flags_fulltext(monkeypatch):
    payload = ('{"resultList":{"result":[{"pmid":"777","pmcid":"PMC77","doi":"10.5/x",'
               '"title":"T","isOpenAccess":"Y","inEPMC":"Y"}]}}')
    monkeypatch.setattr(biblio.net, "fetch_text", lambda *a, **k: payload)
    r = biblio.resolve_europepmc(pmid="777")
    assert r == {"pmid": "777", "pmcid": "PMC77", "doi": "10.5/x", "title": "T", "has_fulltext": True}


def test_resolve_europepmc_is_offline_safe(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(biblio.net, "fetch_text", boom)
    assert biblio.resolve_europepmc(pmid="777") is None
