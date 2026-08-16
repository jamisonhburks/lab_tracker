"""deep_search — cache expensive literature sweeps INTO the primary KG so the lab doesn't redo them.

When a member has Claude "dive deeper" — corroborate against the KG *and* run a broad online
search — that search's harvested knowledge should be DISTILLED into the primary written KG
(kg_writer) with provenance, and the topic marked as searched. Then the next person's query
corroborates against the now-enriched KG instead of repeating the big search.

Division of labor (unchanged from the rest of the substrate):
  - SUBSTRATE (here, no LLM): FETCH (multi-query PubMed), WRITE (rigor-checked into the primary
    KG, attributed, locked), and CACHE (record what's been searched, so it's not repeated).
  - THINKER (the client's Claude): DISTILL — read the fetched abstracts, propose structured
    associations — then submit them to `record_distillation`.

Flow:
  search_status(topic, a, c)          -> already covered? (skip the big online search)
  deep_fetch(topic, [query variants]) -> a corpus of abstracts for the thinker to distill
  record_distillation(topic, [assoc]) -> writes them to the primary KG + caches the topic
"""
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

import kg_writer
import net
import store_lock

ROOT = Path(__file__).parent
CACHE = ROOT / "memory" / "search_cache.jsonl"
_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
COVERAGE_MIN = 3            # >= this many curated edges touching the entities counts as "covered"
STALE_AFTER_DAYS = 180      # literature moves — a cache hit older than this is flagged for refresh


def _age_days(ts: str):
    try:
        return (datetime.now() - datetime.fromisoformat(ts)).days
    except Exception:
        return None


def _append_cache(topic: str, entities, contributor, n_papers: int,
                  n_associations: int, pmids) -> None:
    store_lock.append_jsonl(CACHE, {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "contributor": contributor or "unknown", "topic": topic.strip(),
        "entities": sorted({e for e in (entities or []) if e}),
        "n_papers": n_papers, "n_associations": n_associations, "pmids": list(pmids or [])})


def _pubmed(query: str, n: int) -> list:
    """[{pmid, title, abstract}] for a query — no LLM. Best-effort (empty on failure)."""
    try:
        su = f"{_EUTILS}/esearch.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "term": query, "retmax": n, "retmode": "json"})
        ids = json.loads(net.fetch_text(su, timeout=25))["esearchresult"]["idlist"]
        if not ids:
            return []
        fu = f"{_EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"})
        import xml.etree.ElementTree as ET
        root = ET.fromstring(net.fetch_bytes(fu, timeout=30))
        out = []
        for art in root.findall(".//PubmedArticle"):
            out.append({"pmid": art.findtext(".//PMID") or "",
                        "title": (art.findtext(".//ArticleTitle") or "").strip(),
                        "abstract": " ".join(t.text or "" for t in art.findall(".//AbstractText")).strip()})
        return out
    except Exception:
        return []


def _cache() -> list:
    return [json.loads(l) for l in CACHE.open(encoding="utf-8") if l.strip()] if CACHE.exists() else []


def _cache_hits(topic: str, entities: list) -> list:
    keys = [t.strip().lower() for t in ([topic] + entities) if t and t.strip()]
    hits = []
    for e in _cache():
        hay = (e.get("topic", "") + " " + " ".join(e.get("entities", []))).lower()
        if any(k in hay for k in keys):
            hits.append(e)
    return hits


def _coverage(entities: list) -> int:
    seen = set()
    for ent in entities:
        if not ent:
            continue
        for r in kg_writer.query(ent, None) + kg_writer.query(None, ent):
            seen.add((r["subject"].lower(), r["predicate"].lower(), r["object"].lower()))
    return len(seen)


def search_status(topic: str, subject: str = "", object: str = "") -> str:
    """BEFORE a big online search: is this already covered — by a prior deep search (cache) or by
    existing curated edges? If so, corroborate against the KG and skip the redundant sweep."""
    ents = [subject, object]
    hits = _cache_hits(topic, ents)
    cov = _coverage(ents)
    stale = False
    lines = [f"Search status — topic: {topic!r}" + (f"  ({subject} ↔ {object})" if subject or object else "")]
    if hits:
        h = hits[-1]
        age = _age_days(h.get("ts", ""))
        stale = age is not None and age > STALE_AFTER_DAYS
        lines.append(f"  ALREADY DEEP-SEARCHED: '{h['topic']}' by {h.get('contributor', '?')} on "
                     f"{h.get('ts', '?')[:10]}" + (f" ({age}d ago)" if age is not None else "") +
                     f" — {h.get('n_papers', '?')} papers, {h.get('n_associations', '?')} associations."
                     + ("  ⚠ STALE (literature moves) — a refresh may surface newer papers." if stale else ""))
    lines.append(f"  curated KG coverage for these entities: {cov} edge(s).")
    if hits and stale:
        lines.append("  → COVERED BUT STALE. Refresh: deep_fetch(...) (bias to recent papers), then "
                     "record_distillation(...) — evidence dedups, so re-distilling is cheap and updates the cache.")
    elif hits or cov >= COVERAGE_MIN:
        lines.append("  → COVERED. Corroborate via query_curated_findings / ground_claim; a fresh "
                     "deep search is likely redundant (saves the online sweep).")
    else:
        lines.append("  → NOT yet covered. A deep search would add coverage: deep_fetch(...) then "
                     "distill + record_distillation(...).")
    return "\n".join(lines)


def deep_fetch(topic: str, extra_terms=None, max_papers: int = 8) -> str:
    """Broad multi-query PubMed fetch (NO LLM) — the topic plus any query variants the thinker
    supplies — deduped by PMID. Returns a corpus for the thinker to distill. Records nothing yet
    (call record_distillation with the distilled associations)."""
    terms = [topic] + [t.strip() for t in (extra_terms or []) if t and t.strip()]
    seen, corpus = set(), []
    for q in terms:
        for art in _pubmed(q, max(2, max_papers // max(1, len(terms)))):
            if art["pmid"] and art["pmid"] not in seen and art["abstract"]:
                seen.add(art["pmid"]); corpus.append(art)
    if not corpus:
        return f"No PubMed results for {topic!r} (or its variants). Nothing to distill."
    out = [f"Deep-fetch corpus for {topic!r}: {len(corpus)} paper(s) across {len(terms)} query "
           "variant(s). DISTILL these into structured associations, then call "
           "record_distillation(topic, [{subject,predicate,object,direction,source:PMID,...}])."]
    for a in corpus[:max_papers]:
        out.append(f"\n[PMID:{a['pmid']}] {a['title']}\n  {a['abstract'][:600]}")
    return "\n".join(out)


_JUNK = re.compile(r"^[A-Z]{1,4}\d{3,}$|^\d+$")     # bare accession / number, not an entity


def _ok(a: dict) -> bool:
    s, p, o = a.get("subject", "").strip(), a.get("predicate", "").strip(), a.get("object", "").strip()
    return bool(s and p and o and a.get("source")) and not (_JUNK.match(s) or _JUNK.match(o))


def _normalize(name: str):
    """Resolve a surface form to a canonical KG node {id, name, ...}, or None on a miss.

    Lazy import so this module stays importable without the (heavy) grounding-KG deps, and so a
    missing/absent KG degrades to 'keep the raw string' (closed-world) instead of crashing.
    """
    try:
        import kg_memory
        return kg_memory.normalize_entity(name)
    except Exception:
        return None


def record_distillation(topic: str, associations: list, pmids=None,
                        contributor=None, rigor_verdict=None) -> str:
    """Write the thinker's distilled associations into the PRIMARY KG (kg_writer) with provenance,
    and CACHE the topic so future queries corroborate instead of re-searching.

    Entities are NORMALIZED to canonical KG nodes (like curate_literature) so surface variants
    ('T2DM' vs 'type 2 diabetes') merge into ONE edge instead of fragmenting the evidence. Each
    source's last-author is resolved once and stored as the edge's independence signal
    (research_group). `rigor_verdict` may only TIGHTEN filtering — 'reject' drops the batch — it can
    no longer bypass the structural junk guard (_ok). Literature-evidence layer (queryable
    immediately), not the gated consensus tier."""
    assocs = associations or []
    meta = _resolve_meta(_pmids([a.get("source", "") for a in assocs]))   # last-author per PMID (cached)
    added, skipped, normed = 0, 0, 0
    for a in assocs:
        if rigor_verdict == "reject" or not _ok(a):   # thinker veto OR malformed → skip ('accept' no longer bypasses _ok)
            skipped += 1
            continue
        subj_raw, obj_raw = a["subject"].strip(), a["object"].strip()
        s_norm, o_norm = _normalize(subj_raw), _normalize(obj_raw)
        normed += bool(s_norm) + bool(o_norm)
        src = str(a.get("source", ""))
        pm = _pmids([src])
        rgroup = ((meta.get(pm[0]) or {}).get("last_author") or None) if pm else None
        kg_writer.add_association(
            s_norm["name"] if s_norm else subj_raw,
            a.get("predicate", "associated_with").strip(),
            o_norm["name"] if o_norm else obj_raw,
            source=src, direction=a.get("direction", "supports"),
            sample_size=a.get("sample_size"), effect_size=a.get("effect_size"),
            p_value=a.get("p_value"), risk_of_bias=a.get("risk_of_bias"),
            research_group=rgroup,
            subject_id=s_norm["id"] if s_norm else None,
            object_id=o_norm["id"] if o_norm else None)
        added += 1
    entities = ({a.get("subject", "") for a in assocs} |
                {a.get("object", "") for a in assocs}) - {""}
    n_papers = len(set(pmids or [a.get("source") for a in assocs]))
    _append_cache(topic, entities, contributor, n_papers, added, pmids)
    return (f"Distilled {added} association(s) into the primary KG from topic {topic!r}"
            + (f", {normed} entities normalized to KG nodes" if normed else "")
            + (f" ({skipped} skipped: malformed/no-source/vetoed)" if skipped else "")
            + ". Cached — future queries on this topic corroborate against the KG "
            "(no repeat online search needed).")


def mark_searched(topic: str, pmids=None, n_associations: int = 0,
                  contributor=None, entities=None) -> None:
    """Record that a topic was searched (the associations were written elsewhere — e.g. the local
    agent's curate_literature). Marks the shared cache so the sweep isn't repeated lab-wide."""
    _append_cache(topic, entities, contributor, len(set(pmids or [])), n_associations, pmids)


def stale_topics(older_than_days: int = STALE_AFTER_DAYS) -> list:
    """Topics whose MOST-RECENT cache entry is older than the threshold — candidates for a
    scheduled refresh. Returns [{topic, age_days, ts, contributor}], oldest first."""
    latest = {}
    for e in _cache():
        t = e.get("topic", "")
        if t and (t not in latest or e.get("ts", "") > latest[t].get("ts", "")):
            latest[t] = e
    out = []
    for t, e in latest.items():
        age = _age_days(e.get("ts", ""))
        if age is not None and age > older_than_days:
            out.append({"topic": t, "age_days": age, "ts": e.get("ts", ""),
                        "contributor": e.get("contributor", "?")})
    return sorted(out, key=lambda x: -x["age_days"])


# --------------------------------------------------------------------------- #
# Source independence — group PMIDs by last-author so one group citing itself   #
# doesn't count as N independent sources (used by graduation's rigor bar).      #
# --------------------------------------------------------------------------- #
_META_CACHE = ROOT / "memory" / "pmid_meta.json"


def _pmids(sources) -> list:
    out = []
    for s in sources:
        m = re.search(r"PMID:\s*(\d+)", str(s))
        if m:
            out.append(m.group(1))
    return out


def _fetch_pmid_meta(pmids: list) -> dict:
    """{pmid: {journal, last_author}} from PubMed (no LLM). Best-effort; empty on failure."""
    if not pmids:
        return {}
    try:
        import xml.etree.ElementTree as ET
        fu = f"{_EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
        root = ET.fromstring(net.fetch_bytes(fu, timeout=30))
        out = {}
        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//PMID") or ""
            authors = art.findall(".//AuthorList/Author")
            last = authors[-1].findtext("LastName") if authors else None
            out[pmid] = {"journal": (art.findtext(".//Journal/Title") or "").strip(),
                         "last_author": (last or "").strip()}
        return out
    except Exception:
        return {}


def _resolve_meta(pmids: list) -> dict:
    """PMID metadata with a persisted cache — only uncached ids hit PubMed."""
    cache = {}
    if _META_CACHE.exists():
        try:
            cache = json.loads(_META_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    missing = [p for p in pmids if p not in cache]
    if missing:
        cache.update(_fetch_pmid_meta(missing))
        _META_CACHE.parent.mkdir(parents=True, exist_ok=True)
        try:
            _META_CACHE.write_text(json.dumps(cache), encoding="utf-8")
        except Exception:
            pass
    return {p: cache.get(p, {}) for p in pmids}


def independent_count(sources) -> int:
    """Count INDEPENDENT sources: PMIDs grouped by last-author (same group → 1), plus each
    distinct non-PMID source and each unresolvable PMID. Graceful: if no PMIDs, distinct count."""
    srcs = [str(s) for s in sources if s]
    pmids = _pmids(srcs)
    non_pmid = {s for s in srcs if not re.search(r"PMID:\s*\d+", s)}
    if not pmids:
        return len(set(srcs))
    meta = _resolve_meta(pmids)
    groups, unresolved = set(), 0
    for p in pmids:
        la = (meta.get(p) or {}).get("last_author", "")
        if la:
            groups.add(la.lower())
        else:
            unresolved += 1                       # can't prove same group → count individually
    return len(groups) + unresolved + len(non_pmid)
