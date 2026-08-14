"""ml_ingest — Stage 4: bulk-ingest an external ML method corpus into the fused KG.

Beyond the hand-curated 61 methods (ml_seed.py), this harmonizes a BULK method corpus into
the SAME Method schema, DEDUPED against the curated set, and writes a SEPARATE, lower-trust
seed (seeds/ml_bulk.json). The epistemic distinction is explicit and honest:

  - curated (ml_seed): author-VERIFIED — real first/last author fetched + title-guarded from
    arXiv. High trust.
  - bulk (here): paper-LINKED but NOT author-verified — name, category, year, paper, lineage.
    A deliberate step down; bulk edges are source-tagged 'paperswithcode (bulk)'.

Source. The Papers-with-Code methods dump is the canonical bulk corpus, but PwC was sunset in
2025 and its media URL now 302-redirects to HuggingFace, so the live fetch usually returns
HTML, not the gz. The pipeline TRIES the live dump (through net.py's retries), verifies it is
really gzip-JSON, and on any failure FALLS BACK to a vendored snapshot
(seeds/pwc_methods_sample.json) — real methods not in the curated set. Which path ran is
printed, never silent. Point --url at any PwC-schema mirror to bulk-load the full ~2k taxonomy.

    python ml_ingest.py              # live PwC, else vendored snapshot -> seeds/ml_bulk.json
    python ml_ingest.py --vendored   # force the offline snapshot
    KG_BACKEND=ml_full python agent.py "..."     # curated + bulk merged (see kg_memory)
"""
import argparse
import gzip
import json
import re
from pathlib import Path

import ml_schema
import net

HERE = Path(__file__).parent
VENDORED = HERE / "seeds" / "pwc_methods_sample.json"
OUT = HERE / "seeds" / "ml_bulk.json"
BULK_SOURCE = "paperswithcode (bulk)"           # marks these edges as uncurated/lower-trust
MAX_BULK = 800                                  # cap so a full dump stays tractable

# PwC media (now sunset/redirecting) + a place to drop a mirror. Tried in order.
PWC_URLS = [
    "https://production-media.paperswithcode.com/about/methods.json.gz",
    "https://paperswithcode.com/media/about/methods.json.gz",
]

_AREA2CAT = {
    "general": "Method", "natural language processing": "Model", "computer vision": "Architecture",
    "reinforcement learning": "Method", "graphs": "Architecture", "sequential": "Architecture",
    "audio": "Model", "speech": "Model", "time series": "Architecture", "tabular": "Architecture",
}


def _arxiv_from(text: str) -> str:
    m = re.search(r"(\d{4}\.\d{4,5})", text or "")
    return m.group(1) if m else ""


def _area_to_cat(area: str) -> str:
    return _AREA2CAT.get((area or "").strip().lower(), "Method")


def _normalize_pwc(rec: dict) -> dict:
    """Map one raw PwC methods.json record to our normalized shape. PwC methods.json has no
    explicit parent links, so lineage is empty on the live path (the vendored snapshot adds
    known parents)."""
    paper = rec.get("paper") or {}
    colls = rec.get("collections") or []
    area = (colls[0].get("area") if colls and isinstance(colls[0], dict) else rec.get("area")) or ""
    return {
        "name": rec.get("name"),
        "full_name": rec.get("full_name"),
        "category": _area_to_cat(area),
        "year": rec.get("introduced_year"),
        "arxiv_id": _arxiv_from(paper.get("url", "") or paper.get("title", "")),
        "paper_title": paper.get("title"),
        "area": area,
        "parents": [],
    }


def _fetch_live(urls=PWC_URLS) -> list | None:
    """Try each candidate URL; return normalized records, or None if none yield gzip-JSON."""
    for url in urls:
        try:
            raw = net.fetch_bytes(url, timeout=60)
            if raw[:2] != b"\x1f\x8b":           # not gzip (PwC now serves an HTML redirect)
                print(f"  [live] {url} -> not gzip (likely sunset/redirect); skipping")
                continue
            data = json.loads(gzip.decompress(raw))
            print(f"  [live] {url} -> {len(data)} raw records")
            return [_normalize_pwc(r) for r in data]
        except Exception as err:
            print(f"  [live] {url} -> {type(err).__name__}: {str(err)[:80]}")
    return None


def _load_vendored() -> list:
    return json.loads(VENDORED.read_text(encoding="utf-8"))


def _curated_names() -> set:
    """Lower-cased names already in the curated fused seed (for dedup)."""
    nodes, _ = ml_schema.load_fused_seed()
    return {n[1].lower() for n in nodes if str(n[0]).startswith("METHOD:")}


def _to_methods(normalized: list, curated: set):
    """Harmonize normalized records -> (methods, kept, dropped, deduped). GUARD: require a
    name and a paper (title or arXiv). DEDUP against the curated set. CAP at MAX_BULK."""
    methods, dropped, deduped = [], [], []
    seen = set()
    for rec in normalized:
        name = (rec.get("name") or "").strip()
        has_paper = bool(rec.get("arxiv_id") or rec.get("paper_title"))
        if not name or not has_paper:
            dropped.append(rec.get("name") or "(no name)")
            continue
        key = name.lower()
        if key in curated or key in seen:        # don't shadow a curated (verified) method
            deduped.append(name)
            continue
        seen.add(key)
        if len(methods) >= MAX_BULK:
            dropped.append(f"{name} (over MAX_BULK={MAX_BULK})")
            continue
        intro = f"arXiv:{rec['arxiv_id']}" if rec.get("arxiv_id") else (rec.get("paper_title") or "")
        methods.append(ml_schema.Method(
            name=name, category=rec.get("category") or "Method", year=rec.get("year"),
            intro_paper=intro, derived_from=list(rec.get("parents") or [])))
    return methods, len(methods), dropped, deduped


def _bulk_rows(methods: list):
    """Method rows with every edge source rewritten to the bulk marker (so grounding/trust
    can see these are uncurated). Authorship is intentionally absent — bulk = paper-linked."""
    nodes, edges = [], []
    for m in methods:
        n, e = m.to_rows()
        nodes += n
        edges += [(s, p, o, BULK_SOURCE) for (s, p, o, _src) in e]
    seen, uniq = set(), []
    for r in nodes:
        if r[0] not in seen:
            seen.add(r[0]); uniq.append(r)
    return uniq, edges


def build_bulk(prefer_live: bool = True) -> dict:
    normalized, source = None, "vendored snapshot"
    if prefer_live:
        normalized = _fetch_live()
        if normalized is not None:
            source = "live Papers-with-Code dump"
    if normalized is None:
        normalized = _load_vendored()
        print(f"  [vendored] {VENDORED.name} -> {len(normalized)} records "
              "(live PwC unavailable — sunset/redirect)")
    methods, kept, dropped, deduped = _to_methods(normalized, _curated_names())
    nodes, edges = _bulk_rows(methods)
    OUT.write_text(json.dumps({"source": source, "n_methods": kept,
                               "nodes": nodes, "edges": edges}, indent=2), encoding="utf-8")
    stats = {"source": source, "methods": kept, "dropped": len(dropped),
             "deduped_vs_curated": len(deduped), "nodes": len(nodes), "edges": len(edges)}
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Bulk-ingest ML methods into the fused KG.")
    ap.add_argument("--vendored", action="store_true", help="force the offline snapshot")
    args = ap.parse_args()
    s = build_bulk(prefer_live=not args.vendored)
    print(f"Wrote {OUT} — {s['methods']} bulk methods ({s['source']}); "
          f"{s['nodes']} nodes / {s['edges']} edges; "
          f"deduped {s['deduped_vs_curated']} vs curated, dropped {s['dropped']}.")
