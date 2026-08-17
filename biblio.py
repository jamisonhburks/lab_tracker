"""biblio — the lab's BIBLIOGRAPHIC / PROVENANCE graph: Works keyed by persistent IDs (ADR-0061).

A separate graph layer beside the domain KG. Its nodes are Works (papers; later datasets), each
keyed by a persistent id (canonical preference doi → pmid → pmcid) with a crosswalk so any known id
resolves to the same Work. It answers three questions the domain KG can't:

  1. PAPER-LEVEL DEDUP — have we already ingested THIS exact paper (not just "searched this topic"),
     and for which lab queries? (`seen`, `coverage_of`)
  2. ACCESS LEVEL — did we read the ABSTRACT or the FULL TEXT? (`none < abstract < full_text`,
     upgraded monotonically as a fuller copy is read).
  3. PRECISE SUPPORT — every domain association can link to the Work(s) that support it
     (`link_association` / `supports`), so provenance is a node, not an opaque `PMID:` string.

Pure + best-effort: the registry (crosswalk, access upgrade, dedup, links) is offline and unit
tested; the network resolver (`resolve_europepmc`) sits behind net.py and is stubbed in tests.
Store: memory/biblio/works.jsonl (gitignored). See ADR-0061 for the source tiering.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

import net
import store_lock

ROOT = Path(__file__).parent
STORE = ROOT / "memory" / "biblio" / "works.jsonl"

ACCESS_RANK = {"none": 0, "abstract": 1, "full_text": 2}


# --------------------------------------------------------------------------- #
# ID normalization + canonical keys                                            #
# --------------------------------------------------------------------------- #
def norm_doi(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    return s.strip()


def norm_pmid(s: str) -> str:
    m = re.search(r"(\d+)", str(s or ""))
    return m.group(1) if m else ""


def norm_pmcid(s: str) -> str:
    m = re.search(r"(\d+)", str(s or ""))
    return f"PMC{m.group(1)}" if m else ""


def _tokens(ids: dict) -> list:
    """Ordered xref tokens (canonical preference first): doi > pmid > pmcid."""
    out = []
    if ids.get("doi") and norm_doi(ids["doi"]):
        out.append(f"doi:{norm_doi(ids['doi'])}")
    if ids.get("pmid") and norm_pmid(ids["pmid"]):
        out.append(f"pmid:{norm_pmid(ids['pmid'])}")
    if ids.get("pmcid") and norm_pmcid(ids["pmcid"]):
        out.append(f"pmcid:{norm_pmcid(ids['pmcid'])}")
    if ids.get("openalex"):
        out.append(f"openalex:{str(ids['openalex']).strip()}")
    return out


def _one_token(id_str: str) -> list:
    """Best-effort tokens for a single loose id string (e.g. 'PMID:123' or a bare DOI)."""
    s = str(id_str or "").strip()
    if not s:
        return []
    if s.lower().startswith("pmc") or "pmcid" in s.lower():
        return [f"pmcid:{norm_pmcid(s)}"]
    if re.match(r"^(pmid[:\s]|\d+$)", s.lower()) and norm_pmid(s):
        return [f"pmid:{norm_pmid(s)}"]
    if "/" in s or s.lower().startswith(("10.", "doi", "http")):
        return [f"doi:{norm_doi(s)}"]
    return []


# --------------------------------------------------------------------------- #
# Store IO                                                                      #
# --------------------------------------------------------------------------- #
def _load() -> list:
    if not STORE.exists():
        return []
    return [json.loads(l) for l in STORE.open(encoding="utf-8") if l.strip()]


def _save(works: list) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text("".join(json.dumps(w) + "\n" for w in works), encoding="utf-8")


def _index(works: list) -> dict:
    """Any known xref token -> the Work's stable key."""
    idx = {}
    for w in works:
        for tok in w.get("xrefs", []):
            idx[tok] = w["key"]
    return idx


def _update_work(key: str, **fields) -> dict | None:
    """Set fields on the Work with `key`, under lock. Returns the updated Work or None."""
    with store_lock.critical(STORE):
        works = _load()
        for w in works:
            if w["key"] == key:
                w.update(fields)
                _save(works)
                return w
    return None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Register (upsert with crosswalk merge + monotonic access upgrade)            #
# --------------------------------------------------------------------------- #
def register(ids: dict, *, title: str = "", access: str = "abstract", text_source: str = "",
             lab_query: str = "", contributor: str = "") -> dict:
    """Upsert a Work from any subset of ids (doi/pmid/pmcid/openalex).

    Merges xrefs, upgrades access monotonically (none<abstract<full_text), and records the lab
    query under `coverage` (paper-level dedup). Returns {key, new, access_upgraded, work}.
    """
    toks = _tokens(ids)
    if not toks:
        raise ValueError("register needs at least one of doi/pmid/pmcid/openalex")
    access = access if access in ACCESS_RANK else "abstract"

    with store_lock.critical(STORE):
        works = _load()
        idx = _index(works)
        key = next((idx[t] for t in toks if t in idx), None)

        if key is not None:
            work = next(w for w in works if w["key"] == key)
            new = False
            work["xrefs"] = sorted(set(work.get("xrefs", [])) | set(toks))
            before = work.get("access", "none")
            if ACCESS_RANK[access] > ACCESS_RANK.get(before, 0):
                work["access"] = access
                work["text_source"] = text_source or work.get("text_source", "")
            access_upgraded = ACCESS_RANK[work["access"]] > ACCESS_RANK.get(before, 0)
            if title and not work.get("title"):
                work["title"] = title
            work["last_seen"] = _now()
        else:
            key = toks[0]
            work = {"key": key, "xrefs": sorted(set(toks)), "title": title,
                    "access": access, "text_source": text_source,
                    "coverage": [], "supports": [], "first_seen": _now(), "last_seen": _now()}
            works.append(work)
            new, access_upgraded = True, True

        if lab_query and not any(c.get("lab_query") == lab_query for c in work["coverage"]):
            work["coverage"].append({"lab_query": lab_query, "contributor": contributor or "unknown",
                                     "ts": _now()})
        _save(works)
        return {"key": key, "new": new, "access_upgraded": access_upgraded, "work": work}


# --------------------------------------------------------------------------- #
# Queries                                                                       #
# --------------------------------------------------------------------------- #
def _xrefs_to_ids(xrefs: list) -> dict:
    ids = {}
    for t in xrefs or []:
        kind, _, val = t.partition(":")
        if kind in ("doi", "pmid", "pmcid", "openalex"):
            ids[kind] = val
    return ids


def get(id_str: str) -> dict | None:
    """The Work matching any known id form, or None."""
    toks = _one_token(id_str)
    if not toks:
        return None
    works = _load()
    idx = _index(works)
    key = next((idx[t] for t in toks if t in idx), None)
    return next((w for w in works if w["key"] == key), None) if key else None


def seen(id_str: str, min_access: str = "abstract") -> bool:
    """Have we already ingested this paper at >= `min_access`? (paper-level dedup)."""
    w = get(id_str)
    return bool(w) and ACCESS_RANK.get(w["access"], 0) >= ACCESS_RANK.get(min_access, 1)


def access_of(id_str: str) -> str:
    w = get(id_str)
    return w["access"] if w else "none"


def coverage_of(id_str: str) -> list:
    w = get(id_str)
    return list(w["coverage"]) if w else []


def link_association(id_str: str, assoc_key: str) -> bool:
    """Record that this Work SUPPORTS a domain association (source→claim edge). Idempotent."""
    toks = _one_token(id_str)
    if not toks or not assoc_key:
        return False
    with store_lock.critical(STORE):
        works = _load()
        idx = _index(works)
        key = next((idx[t] for t in toks if t in idx), None)
        if key is None:
            return False
        work = next(w for w in works if w["key"] == key)
        if assoc_key not in work.setdefault("supports", []):
            work["supports"].append(assoc_key)
            _save(works)
        return True


def supporters_of(assoc_key: str) -> list:
    """Every Work that supports a given association key — 'where does support come from'."""
    return [w for w in _load() if assoc_key in w.get("supports", [])]


def stats() -> dict:
    works = _load()
    by_access = {a: 0 for a in ACCESS_RANK}
    for w in works:
        by_access[w.get("access", "none")] = by_access.get(w.get("access", "none"), 0) + 1
    return {"works": len(works), "by_access": by_access,
            "links": sum(len(w.get("supports", [])) for w in works),
            "citations": sum(len(w.get("cites", [])) for w in works)}


# --------------------------------------------------------------------------- #
# Resolver — Europe PMC (best-effort, network; stubbed in tests)               #
# --------------------------------------------------------------------------- #
_EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def enrich(id_str: str, resolver=None) -> dict | None:
    """Backfill a registered Work's crosswalk (DOI/PMCID) + full-text availability via a resolver.

    Best-effort and idempotent: a no-op if the Work is unknown, already carries a DOI, or the
    resolver returns nothing (offline-safe). `resolver` is injectable for testing; defaults to
    Europe PMC. Sets `fulltext_available` (the full text EXISTS) — distinct from `access` (we've
    READ it): knowing a full text exists is not the same as having ingested it."""
    resolver = resolver or resolve_europepmc
    w = get(id_str)
    if w is None:
        return None
    if any(t.startswith("doi:") for t in w.get("xrefs", [])):
        return w                                   # already has a DOI — nothing to backfill
    key = w["key"]
    pmid = next((t.split(":", 1)[1] for t in w["xrefs"] if t.startswith("pmid:")), "")
    if not pmid:
        return w
    meta = resolver(pmid=pmid)
    if not meta:
        return w
    register({"pmid": meta.get("pmid") or pmid, "doi": meta.get("doi"),
              "pmcid": meta.get("pmcid")}, title=meta.get("title", ""))   # merges crosswalk in
    if meta.get("has_fulltext"):
        _update_work(key, fulltext_available=True)
    return get(id_str)


def resolve_europepmc(pmid: str = "", doi: str = "") -> dict | None:
    """Crosswalk a PMID/DOI via Europe PMC → {pmid, pmcid, doi, title, has_fulltext}.
    Best-effort: returns None on any failure (offline-safe)."""
    if pmid:
        query = f"EXT_ID:{norm_pmid(pmid)} AND SRC:MED"
    elif doi:
        query = f'DOI:"{norm_doi(doi)}"'
    else:
        return None
    try:
        import urllib.parse
        url = (f"{_EPMC}/search?" +
               urllib.parse.urlencode({"query": query, "format": "json", "resultType": "core",
                                       "pageSize": 1}))
        res = json.loads(net.fetch_text(url, timeout=25)).get("resultList", {}).get("result", [])
        if not res:
            return None
        r = res[0]
        # full text is readable in EPMC when it's OA and hosted in EPMC
        has_ft = (str(r.get("isOpenAccess", "")).upper() == "Y"
                  and str(r.get("inEPMC", "")).upper() == "Y")
        return {"pmid": norm_pmid(r.get("pmid", "")), "pmcid": (r.get("pmcid") or ""),
                "doi": norm_doi(r.get("doi", "")), "title": (r.get("title") or "").strip(),
                "has_fulltext": has_ft}
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Full-text access (ADR-0061 #2): OA lookup (Unpaywall) + full-text fetch       #
# (Europe PMC), upgrading `access` to full_text only when we actually READ it.  #
# --------------------------------------------------------------------------- #
_UNPAYWALL = "https://api.unpaywall.org/v2"


def resolve_unpaywall(doi: str = "", email: str = "") -> dict | None:
    """OA status for a DOI via Unpaywall → {is_oa, oa_status, oa_url}. Needs a contact email
    (arg or UNPAYWALL_EMAIL); returns None without one, or on any failure (offline-safe)."""
    email = email or os.environ.get("UNPAYWALL_EMAIL", "")
    doi = norm_doi(doi)
    if not doi or not email:
        return None
    try:
        url = f"{_UNPAYWALL}/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"
        d = json.loads(net.fetch_text(url, timeout=25))
        best = d.get("best_oa_location") or {}
        return {"is_oa": bool(d.get("is_oa")), "oa_status": d.get("oa_status") or "",
                "oa_url": best.get("url_for_pdf") or best.get("url") or ""}
    except Exception:
        return None


def oa_status(id_str: str, email: str = "", resolver=None) -> dict | None:
    """Look up + store OA availability for a Work's DOI (Unpaywall). Sets oa_status/oa_url and, when
    open, fulltext_available. Returns the OA info or None. `resolver` injectable for tests."""
    resolver = resolver or resolve_unpaywall
    w = get(id_str)
    if w is None:
        return None
    doi = next((t.split(":", 1)[1] for t in w["xrefs"] if t.startswith("doi:")), "")
    if not doi:
        return None
    info = resolver(doi=doi, email=email)
    if not info:
        return None
    updates = {"oa_status": info.get("oa_status", ""), "oa_url": info.get("oa_url", "")}
    if info.get("is_oa"):
        updates["fulltext_available"] = True
    _update_work(w["key"], **updates)
    return info


def _strip_xml(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _fetch_fulltext_europepmc(pmcid: str) -> str | None:
    try:
        url = f"{_EPMC}/PMC/{norm_pmcid(pmcid)}/fullTextXML"
        return _strip_xml(net.fetch_text(url, timeout=40)) or None
    except Exception:
        return None


def fetch_fulltext(id_str: str, fetcher=None) -> str | None:
    """Fetch a Work's full text (Europe PMC OA XML by PMCID) and upgrade its access → full_text.
    Returns the text on success, else None. Best-effort/offline-safe; `fetcher` injectable."""
    fetcher = fetcher or _fetch_fulltext_europepmc
    w = get(id_str)
    if w is None:
        return None
    pmcid = next((t.split(":", 1)[1] for t in w["xrefs"] if t.startswith("pmcid:")), "")
    if not pmcid:
        return None
    text = fetcher(pmcid)
    if not text:
        return None
    register({"pmcid": pmcid}, access="full_text", text_source="europepmc:fullTextXML")
    return text


def mark_fulltext(id_str: str, text_source: str = "external") -> dict | None:
    """Record that the full text was READ (upgrade access → full_text) — for full text obtained
    outside the Europe PMC path (a publisher PDF, a manual read, etc.)."""
    w = get(id_str)
    if w is None:
        return None
    return register(_xrefs_to_ids(w["xrefs"]), access="full_text", text_source=text_source)["work"]


# --------------------------------------------------------------------------- #
# Citation edges (ADR-0061 #4): Work —cites→ Work, for support-chain tracing.   #
# OpenCitations by default; resolver is injectable (e.g. OpenAlex) + testable.  #
# --------------------------------------------------------------------------- #
_OPENCITATIONS = "https://opencitations.net/index/coci/api/v1"


def resolve_citations(doi: str) -> list:
    """DOIs this DOI cites (outgoing references) via OpenCitations COCI. Best-effort → [] on any
    failure (offline-safe)."""
    doi = norm_doi(doi)
    if not doi:
        return []
    try:
        url = f"{_OPENCITATIONS}/references/{urllib.parse.quote(doi)}"
        data = json.loads(net.fetch_text(url, timeout=30))
        return [d for row in data if (d := norm_doi(row.get("cited", "")))]
    except Exception:
        return []


def add_citation(from_id: str, to_doi: str) -> bool:
    """Record from_id —cites→ to_doi (a DOI). Idempotent; True if the citing Work exists."""
    to = norm_doi(to_doi)
    if not to:
        return False
    with store_lock.critical(STORE):
        works = _load()
        idx = _index(works)
        key = next((idx[t] for t in _one_token(from_id) if t in idx), None)
        if key is None:
            return False
        w = next(x for x in works if x["key"] == key)
        cites = w.setdefault("cites", [])
        if to not in cites:
            cites.append(to)
            _save(works)
        return True


def fetch_citations(id_str: str, resolver=None) -> list:
    """Populate a Work's outgoing citations (by its DOI) via the resolver. Returns the cited DOIs."""
    resolver = resolver or resolve_citations
    w = get(id_str)
    if w is None:
        return []
    doi = next((t.split(":", 1)[1] for t in w["xrefs"] if t.startswith("doi:")), "")
    if not doi:
        return []
    cited = resolver(doi)
    for cd in cited:
        add_citation(id_str, cd)
    return cited


def cites_of(id_str: str) -> list:
    w = get(id_str)
    return list(w.get("cites", [])) if w else []


def cited_by(id_str: str) -> list:
    """Works in the store that cite this one (by any of its DOIs) — the incoming edges."""
    w = get(id_str)
    if w is None:
        return []
    dois = {t.split(":", 1)[1] for t in w["xrefs"] if t.startswith("doi:")}
    return [x for x in _load() if dois & set(x.get("cites", []))] if dois else []
