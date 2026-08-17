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
import re
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
            "links": sum(len(w.get("supports", [])) for w in works)}


# --------------------------------------------------------------------------- #
# Resolver — Europe PMC (best-effort, network; stubbed in tests)               #
# --------------------------------------------------------------------------- #
_EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"


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
