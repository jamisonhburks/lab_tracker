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


# --------------------------------------------------------------------------- #
# enrich — backfill crosswalk + full-text availability                         #
# --------------------------------------------------------------------------- #
def _fake_resolver(**expected):
    def r(pmid="", doi=""):
        return {"pmid": pmid, "pmcid": "PMC88", "doi": "10.7/enriched",
                "title": "Resolved", "has_fulltext": True}
    return r


def test_enrich_backfills_doi_pmcid_and_fulltext_flag():
    biblio.register({"pmid": "888"}, access="abstract", lab_query="q")
    w = biblio.enrich("888", resolver=_fake_resolver())
    assert "doi:10.7/enriched" in w["xrefs"] and "pmcid:PMC88" in w["xrefs"]
    assert w["fulltext_available"] is True
    assert biblio.get("10.7/enriched")["key"] == "pmid:888"   # still ONE work, found by DOI now
    assert len(biblio._load()) == 1


def test_enrich_is_noop_when_already_has_doi():
    biblio.register({"pmid": "889", "doi": "10.1/known"}, lab_query="q")
    called = []
    w = biblio.enrich("889", resolver=lambda **k: called.append(1) or {"doi": "10.9/other"})
    assert not called                                # resolver never consulted
    assert "doi:10.9/other" not in w["xrefs"]


def test_enrich_is_offline_safe():
    biblio.register({"pmid": "890"}, lab_query="q")
    w = biblio.enrich("890", resolver=lambda **k: None)   # resolver failed / offline
    assert w["access"] == "abstract" and not any(t.startswith("doi:") for t in w["xrefs"])
    assert biblio.enrich("does-not-exist", resolver=_fake_resolver()) is None


# --------------------------------------------------------------------------- #
# full-text access + OA (Unpaywall stubbed, full-text fetcher stubbed)         #
# --------------------------------------------------------------------------- #
def test_oa_status_stores_availability():
    biblio.register({"pmid": "900", "doi": "10.1/oa"}, lab_query="q")
    info = biblio.oa_status("900", email="x@y.z",
                            resolver=lambda doi, email: {"is_oa": True, "oa_status": "gold",
                                                          "oa_url": "http://pdf"})
    assert info["is_oa"]
    w = biblio.get("900")
    assert w["oa_status"] == "gold" and w["oa_url"] == "http://pdf" and w["fulltext_available"]


def test_oa_status_needs_a_doi():
    biblio.register({"pmid": "901"}, lab_query="q")     # no DOI on this Work
    assert biblio.oa_status("901", email="x@y.z", resolver=lambda **k: {"is_oa": True}) is None


def test_resolve_unpaywall_requires_email(monkeypatch):
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    assert biblio.resolve_unpaywall(doi="10.1/x") is None   # no email → no polite call


def test_fetch_fulltext_upgrades_access():
    biblio.register({"pmid": "902", "pmcid": "PMC902"}, access="abstract", lab_query="q")
    assert biblio.access_of("902") == "abstract"
    text = biblio.fetch_fulltext("902", fetcher=lambda pmcid: "FULL BODY TEXT")
    assert text == "FULL BODY TEXT"
    assert biblio.access_of("902") == "full_text"
    w = biblio.get("902")
    assert w["text_source"] == "europepmc:fullTextXML"


def test_fetch_fulltext_needs_pmcid_and_is_offline_safe():
    biblio.register({"pmid": "903"}, access="abstract", lab_query="q")   # no PMCID
    assert biblio.fetch_fulltext("903", fetcher=lambda pmcid: "x") is None
    biblio.register({"pmid": "904", "pmcid": "PMC904"}, lab_query="q")
    assert biblio.fetch_fulltext("904", fetcher=lambda pmcid: None) is None   # fetch failed
    assert biblio.access_of("904") == "abstract"                              # not upgraded


def test_mark_fulltext_upgrades_access():
    biblio.register({"pmid": "905"}, access="abstract", lab_query="q")
    biblio.mark_fulltext("905", text_source="publisher-pdf")
    assert biblio.access_of("905") == "full_text"
    assert biblio.get("905")["text_source"] == "publisher-pdf"


def test_strip_xml():
    assert biblio._strip_xml("<a>hello   <b>world</b></a>") == "hello world"


# --------------------------------------------------------------------------- #
# citation edges (OpenCitations stubbed)                                        #
# --------------------------------------------------------------------------- #
def test_resolve_citations_parses_opencitations(monkeypatch):
    payload = '[{"cited":"10.1/a"},{"cited":"https://doi.org/10.2/B"},{"cited":""}]'
    monkeypatch.setattr(biblio.net, "fetch_text", lambda *a, **k: payload)
    assert biblio.resolve_citations("10.9/citing") == ["10.1/a", "10.2/b"]


def test_resolve_citations_offline_safe(monkeypatch):
    monkeypatch.setattr(biblio.net, "fetch_text", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert biblio.resolve_citations("10.9/x") == []
    assert biblio.resolve_citations("") == []


def test_fetch_and_query_citation_edges():
    biblio.register({"pmid": "1", "doi": "10.1/citing"}, lab_query="q")
    biblio.register({"pmid": "2", "doi": "10.2/cited"}, lab_query="q")   # the cited paper is also a Work
    cited = biblio.fetch_citations("10.1/citing", resolver=lambda doi: ["10.2/cited", "10.3/external"])
    assert set(cited) == {"10.2/cited", "10.3/external"}
    assert set(biblio.cites_of("1")) == {"10.2/cited", "10.3/external"}
    # incoming edge: the cited Work sees paper 1 as a citer (keyed by DOI — canonical preference)
    cb = biblio.cited_by("10.2/cited")
    assert len(cb) == 1 and cb[0]["key"] == "doi:10.1/citing"


def test_add_citation_idempotent_and_guards():
    biblio.register({"pmid": "10", "doi": "10.1/c"}, lab_query="q")
    assert biblio.add_citation("10", "10.5/x")
    assert biblio.add_citation("10", "10.5/x")           # idempotent
    assert biblio.cites_of("10") == ["10.5/x"]
    assert biblio.add_citation("999", "10.5/x") is False  # unknown citing Work
    assert biblio.add_citation("10", "") is False         # no target doi


def test_stats_counts_citations():
    biblio.register({"pmid": "1", "doi": "10.1/a"}, lab_query="q")
    biblio.add_citation("1", "10.2/b")
    assert biblio.stats()["citations"] == 1
