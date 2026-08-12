"""Ontological memory: a typed knowledge graph the agent can traverse.

Unlike episodic/semantic memory (which the agent WRITES from its own runs), this
is a read-only, curated grounding KB — OptimusKG (Zitnik Lab). We query it for:
  - query_graph(entity)     -> typed neighbors  (disease -associated_with-> gene)
  - find_paths(a, c)        -> A->B->C chains    (the Swanson/Rephetio move)

The graph is two Polars DataFrames (nodes, edges) in Biolink shape. Column roles
are named once below, so the same traversal code runs on our demo graph and on
the real OptimusKG tables — swapping backends is one function (`load_optimuskg`).

Traversal is UNDIRECTED on purpose: for hypothesis generation we care that two
entities are connected through some mechanism, not which way the edge points.
"""

import polars as pl

# Logical role -> column name. Retune to the real OptimusKG schema once the
# background poller confirms it (see optimus_poll output).
NODE_ID, NODE_NAME, NODE_CAT = "id", "name", "category"
EDGE_SUBJ, EDGE_PRED, EDGE_OBJ, EDGE_SRC = "subject", "predicate", "object", "source"

_G = {"nodes": None, "edges": None}


# --------------------------------------------------------------------------- #
# Backends — same interface, different data.                                   #
# --------------------------------------------------------------------------- #

def load_optimuskg(lcc: bool = True) -> None:
    """Swap in the real Zitnik-lab graph. One call; traversal code unchanged."""
    import optimuskg
    nodes, edges = optimuskg.load_graph(lcc=lcc)
    _G["nodes"], _G["edges"] = nodes, edges


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


def _graph() -> tuple:
    if _G["edges"] is None:
        load_demo()
    return _G["nodes"], _G["edges"]


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _resolve(name: str) -> str | None:
    """Map a free-text entity to a node id (exact id, else case-insensitive name)."""
    nodes, _ = _graph()
    if name in nodes[NODE_ID].to_list():
        return name
    hits = nodes.filter(pl.col(NODE_NAME).str.to_lowercase() == name.lower())
    if hits.height == 0:  # fall back to substring
        hits = nodes.filter(pl.col(NODE_NAME).str.to_lowercase().str.contains(name.lower()))
    return hits[NODE_ID][0] if hits.height else None


def _label(node_id: str) -> str:
    nodes, _ = _graph()
    row = nodes.filter(pl.col(NODE_ID) == node_id)
    return f"{row[NODE_NAME][0]} ({row[NODE_CAT][0]})" if row.height else node_id


def _adjacency(node_id: str) -> list:
    """Undirected neighbors of a node: (neighbor_id, predicate, arrow, source)."""
    _, edges = _graph()
    out = edges.filter(pl.col(EDGE_SUBJ) == node_id)
    inc = edges.filter(pl.col(EDGE_OBJ) == node_id)
    nbrs = []
    for r in out.iter_rows(named=True):
        nbrs.append((r[EDGE_OBJ], r[EDGE_PRED], "->", r[EDGE_SRC]))
    for r in inc.iter_rows(named=True):
        nbrs.append((r[EDGE_SUBJ], r[EDGE_PRED], "<-", r[EDGE_SRC]))
    return nbrs


# --------------------------------------------------------------------------- #
# Tools the agent calls                                                        #
# --------------------------------------------------------------------------- #

def query_graph(entity: str) -> str:
    """Return an entity's typed neighbors in the knowledge graph, with sources."""
    node_id = _resolve(entity)
    if node_id is None:
        return f"'{entity}' not found in the knowledge graph."

    lines = [f"{_label(node_id)}  [{node_id}]"]
    for nbr, pred, arrow, src in _adjacency(node_id):
        lines.append(f"  {arrow} {pred} {arrow} {_label(nbr)}   (source: {src})")
    return "\n".join(lines) if len(lines) > 1 else lines[0] + "\n  (no edges)"


def find_paths(entity_a: str, entity_c: str, max_len: int = 3) -> str:
    """Find connecting paths A..C up to max_len edges — the A->B->C discovery move."""
    a, c = _resolve(entity_a), _resolve(entity_c)
    if a is None or c is None:
        missing = entity_a if a is None else entity_c
        return f"'{missing}' not found in the knowledge graph."

    paths = []  # each: list of (from_id, pred, arrow, source, to_id)
    stack = [(a, [], {a})]
    while stack:
        node, trail, seen = stack.pop()
        if len(trail) > max_len:
            continue
        if node == c and trail:
            paths.append(trail)
            continue
        for nbr, pred, arrow, src in _adjacency(node):
            if nbr in seen:
                continue
            stack.append((nbr, trail + [(node, pred, arrow, src, nbr)], seen | {nbr}))

    if not paths:
        return f"No path found between {_label(a)} and {_label(c)} within {max_len} hops."

    paths.sort(key=len)
    out = [f"Paths from {_label(a)} to {_label(c)} (<= {max_len} hops):"]
    for p in paths[:8]:
        chain = _label(p[0][0])
        srcs = []
        for _, pred, arrow, src, to_id in p:
            chain += f"  —{pred}{'→' if arrow == '->' else '←'}  {_label(to_id)}"
            srcs.append(src)
        out.append(f"  • {chain}\n      via: {', '.join(dict.fromkeys(srcs))}")
    return "\n".join(out)
