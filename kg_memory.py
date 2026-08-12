"""Ontological memory: a typed knowledge graph the agent can traverse.

Unlike episodic/semantic memory (which the agent WRITES from its own runs), this
is a read-only, curated grounding KB. We query it for:
  - query_graph(entity)     -> typed neighbors  (disease -associates-> gene)
  - find_paths(a, c)        -> A->B->C chains    (the Swanson/Rephetio move)

The graph is two Polars DataFrames (nodes, edges); column roles are named once
below, so the same traversal code runs on every backend:
  - load_demo()       tiny hand-built graph (offline, instant)
  - load_hetionet()   Hetionet v1.0 (47k nodes / 2.25M edges, CC0) — real data
  - load_optimuskg()  OptimusKG (Zitnik Lab) — pending Dataverse recovery

Pick a backend with the KG_BACKEND env var (demo | hetionet | optimuskg);
default is demo. Traversal is UNDIRECTED on purpose: for hypothesis generation we
care that two entities are connected through some mechanism, not edge direction.

Adjacency and node metadata are indexed once per loaded graph so traversal stays
fast on millions of edges.
"""

import bz2
import json
import os
import shutil
import urllib.request
from collections import deque
from pathlib import Path

import polars as pl

NODE_ID, NODE_NAME, NODE_CAT = "id", "name", "category"
EDGE_SUBJ, EDGE_PRED, EDGE_OBJ, EDGE_SRC = "subject", "predicate", "object", "source"

DATA_DIR = Path(__file__).parent / "data"
HETIONET_URL = (
    "https://media.githubusercontent.com/media/hetio/hetionet/main/"
    "hetnet/json/hetionet-v1.0.json.bz2"
)

_G = {"nodes": None, "edges": None}
_ADJ = None    # id -> [(neighbor_id, predicate, arrow, source)]  (built once)
_META = None   # id -> (name, category)                          (built once)


def _reset() -> None:
    global _ADJ, _META
    _ADJ = _META = None


# --------------------------------------------------------------------------- #
# Backends — same interface, different data.                                   #
# --------------------------------------------------------------------------- #

def load_demo() -> None:
    """A tiny biomedical graph in the same shape, for building/testing offline."""
    _G["nodes"] = pl.DataFrame(
        {
            NODE_ID:   ["MONDO:AF", "HGNC:PITX2", "HGNC:KCNQ1", "DRUG:flecainide",
                        "MONDO:stroke", "HP:palpitations", "DRUG:warfarin"],
            NODE_NAME: ["atrial fibrillation", "PITX2", "KCNQ1", "flecainide",
                        "ischemic stroke", "palpitations", "warfarin"],
            NODE_CAT:  ["Disease", "Gene", "Gene", "Drug",
                        "Disease", "Phenotype", "Drug"],
        }
    )
    _G["edges"] = pl.DataFrame(
        {
            EDGE_SUBJ: ["MONDO:AF", "MONDO:AF", "MONDO:AF", "MONDO:AF",
                        "HGNC:KCNQ1", "MONDO:AF", "DRUG:warfarin", "DRUG:warfarin"],
            EDGE_PRED: ["associated_with", "associated_with", "has_phenotype",
                        "treated_by", "associated_with", "predisposes_to",
                        "treats", "prevents"],
            EDGE_OBJ:  ["HGNC:PITX2", "HGNC:KCNQ1", "HP:palpitations",
                        "DRUG:flecainide", "MONDO:stroke", "MONDO:stroke",
                        "MONDO:AF", "MONDO:stroke"],
            EDGE_SRC:  ["GWAS Catalog", "GWAS Catalog", "HPO", "DrugCentral",
                        "GWAS Catalog", "cohort study", "DrugCentral", "DrugBank"],
        }
    )
    _reset()


def load_hetionet() -> None:
    """Load Hetionet v1.0 from its JSON (downloaded + cached on first use)."""
    DATA_DIR.mkdir(exist_ok=True)
    local = DATA_DIR / "hetionet-v1.0.json.bz2"
    if not local.exists():
        req = urllib.request.Request(HETIONET_URL, headers={"User-Agent": "curl"})
        with urllib.request.urlopen(req, timeout=180) as r, open(local, "wb") as out:
            shutil.copyfileobj(r, out)

    with bz2.open(local, "rt", encoding="utf-8") as f:
        graph = json.load(f)

    # nodes: id = "<Kind>:<identifier>", name, category = kind
    n = graph["nodes"]
    _G["nodes"] = pl.DataFrame(
        {
            NODE_ID:   [f"{x['kind']}:{x['identifier']}" for x in n],
            NODE_NAME: [x.get("name") or str(x["identifier"]) for x in n],
            NODE_CAT:  [x["kind"] for x in n],
        }
    )

    # edges: keep the reporting source(s) as provenance
    def _src(d: dict) -> str:
        s = d.get("source")
        if s:
            return s
        ss = d.get("sources")
        return ", ".join(ss) if isinstance(ss, list) else (ss or "Hetionet")

    e = graph["edges"]
    _G["edges"] = pl.DataFrame(
        {
            EDGE_SUBJ: [f"{x['source_id'][0]}:{x['source_id'][1]}" for x in e],
            EDGE_PRED: [x["kind"] for x in e],
            EDGE_OBJ:  [f"{x['target_id'][0]}:{x['target_id'][1]}" for x in e],
            EDGE_SRC:  [_src(x.get("data", {})) for x in e],
        }
    )
    _reset()


def load_optimuskg(lcc: bool = True) -> None:
    """Swap in the OptimusKG graph. One call; traversal code unchanged."""
    import optimuskg
    _G["nodes"], _G["edges"] = optimuskg.load_graph(lcc=lcc)
    _reset()


_BACKENDS = {"demo": load_demo, "hetionet": load_hetionet, "optimuskg": load_optimuskg}


def _graph() -> tuple:
    if _G["edges"] is None:
        _BACKENDS.get(os.environ.get("KG_BACKEND", "demo").lower(), load_demo)()
    return _G["nodes"], _G["edges"]


# --------------------------------------------------------------------------- #
# Indexes — built once per loaded graph so traversal is O(1) per hop.          #
# --------------------------------------------------------------------------- #

def _meta() -> dict:
    global _META
    if _META is None:
        nodes, _ = _graph()
        _META = dict(zip(nodes[NODE_ID].to_list(),
                         zip(nodes[NODE_NAME].to_list(), nodes[NODE_CAT].to_list())))
    return _META


def _index() -> dict:
    global _ADJ
    if _ADJ is None:
        _, edges = _graph()
        adj: dict = {}
        subj = edges[EDGE_SUBJ].to_list()
        pred = edges[EDGE_PRED].to_list()
        obj = edges[EDGE_OBJ].to_list()
        src = edges[EDGE_SRC].to_list()
        for s, p, o, sc in zip(subj, pred, obj, src):
            adj.setdefault(s, []).append((o, p, "->", sc))
            adj.setdefault(o, []).append((s, p, "<-", sc))
        _ADJ = adj
    return _ADJ


def _resolve(name: str) -> str | None:
    """Map free-text to a node id (exact id, exact name, then substring)."""
    meta = _meta()
    if name in meta:
        return name
    low = name.lower()
    exact = [nid for nid, (nm, _) in meta.items() if nm.lower() == low]
    if exact:
        return exact[0]
    sub = [nid for nid, (nm, _) in meta.items() if low in nm.lower()]
    return sub[0] if sub else None


def _label(node_id: str) -> str:
    nm, cat = _meta().get(node_id, (node_id, "?"))
    return f"{nm} ({cat})"


# --------------------------------------------------------------------------- #
# Tools the agent calls                                                        #
# --------------------------------------------------------------------------- #

def query_graph(entity: str, max_neighbors: int = 40) -> str:
    """Return an entity's typed neighbors in the knowledge graph, with sources."""
    node_id = _resolve(entity)
    if node_id is None:
        return f"'{entity}' not found in the knowledge graph."

    nbrs = _index().get(node_id, [])
    lines = [f"{_label(node_id)}  [{node_id}]  ({len(nbrs)} edges)"]
    for nbr, pred, arrow, src in nbrs[:max_neighbors]:
        lines.append(f"  {arrow} {pred} {arrow} {_label(nbr)}   (source: {src})")
    if len(nbrs) > max_neighbors:
        lines.append(f"  ... and {len(nbrs) - max_neighbors} more")
    return "\n".join(lines)


def find_paths(entity_a: str, entity_c: str, max_len: int = 3,
               max_paths: int = 20, max_expand: int = 60000) -> str:
    """Find connecting paths A..C — the A->B->C discovery move.

    Bounded breadth-first (shortest paths first), with caps so a dense real graph
    can't blow up: stop after `max_paths` found or `max_expand` nodes expanded.
    """
    a, c = _resolve(entity_a), _resolve(entity_c)
    if a is None or c is None:
        missing = entity_a if a is None else entity_c
        return f"'{missing}' not found in the knowledge graph."

    adj = _index()
    paths, expanded, truncated = [], 0, False
    queue = deque([(a, [], frozenset([a]))])
    while queue and len(paths) < max_paths:
        if expanded >= max_expand:
            truncated = True
            break
        node, trail, seen = queue.popleft()
        expanded += 1
        if len(trail) >= max_len:
            continue
        for nbr, pred, arrow, src in adj.get(node, []):
            if nbr in seen:
                continue
            step = trail + [(node, pred, arrow, src, nbr)]
            if nbr == c:
                paths.append(step)
                if len(paths) >= max_paths:
                    break
            elif len(step) < max_len:   # don't enqueue dead-ends at max depth
                queue.append((nbr, step, seen | {nbr}))

    if not paths:
        note = " (search truncated)" if truncated else ""
        return f"No path between {_label(a)} and {_label(c)} within {max_len} hops{note}."

    paths.sort(key=len)
    out = [f"Paths from {_label(a)} to {_label(c)} (<= {max_len} hops):"]
    for p in paths[:8]:
        chain = _label(p[0][0])
        srcs = []
        for _, pred, arrow, src, to_id in p:
            chain += f"  —{pred}{'→' if arrow == '->' else '←'}  {_label(to_id)}"
            srcs.append(src)
        out.append(f"  • {chain}\n      via: {', '.join(dict.fromkeys(srcs))}")
    if truncated:
        out.append("  (search truncated at the expansion cap — more paths may exist)")
    return "\n".join(out)
