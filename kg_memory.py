"""Ontological memory: a typed knowledge graph the agent can traverse.

Unlike episodic/semantic memory (which the agent WRITES from its own runs), this
is a read-only, curated grounding KB. We query it for:
  - query_graph(entity)     -> typed neighbors  (disease -associates-> gene)
  - find_paths(a, c)        -> A->B->C chains    (the Swanson/Rephetio move)

The graph is two Polars DataFrames (nodes, edges); column roles are named once
below, so the same traversal code runs on every backend:
  - load_demo()       tiny hand-built graph (offline, instant)
  - load_hetionet()   Hetionet v1.0 (47k nodes / 2.25M edges, CC0) — GWAS-rich
  - load_monarch()    Monarch KG human subgraph (~148k nodes / 1.9M edges) — 36k
                      MONDO diseases + HPO phenotypes; strong for phenotype/Mendelian
  - load_combined()   Hetionet + Monarch harmonized (genes->Entrez, diseases->MONDO,
                      drugs->CHEBI): ~174k nodes / 4.2M edges — GWAS + phenotype +
                      drug edges on shared nodes (a local slice of PrimeKG)
  - load_optimuskg()  OptimusKG (Zitnik Lab) — pending Dataverse recovery

Pick a backend with KG_BACKEND (demo | hetionet | monarch | combined | optimuskg);
default is demo. Traversal is UNDIRECTED on purpose: for hypothesis generation we
care that two entities are connected through some mechanism, not edge direction.

Adjacency and node metadata are indexed once per loaded graph so traversal stays
fast on millions of edges.
"""

import bz2
import json
import os
import re
import shutil
import urllib.request
from collections import deque
from pathlib import Path

import polars as pl

import net

NODE_ID, NODE_NAME, NODE_CAT = "id", "name", "category"
EDGE_SUBJ, EDGE_PRED, EDGE_OBJ, EDGE_SRC = "subject", "predicate", "object", "source"

DATA_DIR = Path(__file__).parent / "data"
HETIONET_URL = (
    "https://media.githubusercontent.com/media/hetio/hetionet/main/"
    "hetnet/json/hetionet-v1.0.json.bz2"
)
MONARCH_URL = "https://data.monarchinitiative.org/monarch-kg/latest/monarch-kg.tar.gz"

# Monarch is 1.6M nodes / 15.8M edges across many species. For disease-mechanism
# hypothesis generation we keep the HUMAN disease/gene/phenotype/chemical core — this
# drops cross-species orthology, GO-annotation, and anatomical-expression edges that
# would only add hub noise, and keeps it tractable in memory (~Hetionet scale).
_MONARCH_KEEP_CAT = {"Disease", "Gene", "PhenotypicFeature", "Protein",
                     "ChemicalEntity", "Pathway"}
_MONARCH_HUMAN = "NCBITaxon:9606"
# Ontology taxonomy / equivalence predicates — NOT mechanism. Dropped so two diseases
# connect through a shared gene/phenotype, never through a shared ontological ancestor
# (the same reason Hetionet carries no is_a). Keeps find_paths hypotheses mechanistic.
_MONARCH_DROP_PRED = {"subclass_of", "same_as", "homologous_to", "orthologous_to",
                      "related_to", "close_match", "exact_match", "broad_match",
                      "narrow_match", "has_mode_of_inheritance"}

_G = {"nodes": None, "edges": None}
_ADJ = None    # id -> [(neighbor_id, predicate, arrow, source)]  (built once)
_META = None   # id -> (name, category)                          (built once)
_NORM = None   # cleaned_name -> id  (for entity normalization)   (built once)


def _reset() -> None:
    global _ADJ, _META, _NORM
    _ADJ = _META = _NORM = None


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
        with net.urlopen_retry(req, timeout=180) as r, open(local, "wb") as out:
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


def load_monarch(human_only: bool = True) -> None:
    """Load a focused human subgraph of the Monarch KG (disease/gene/phenotype/
    chemical). Named nodes (MONDO diseases, HPO phenotypes, HGNC-symbol genes) and
    real per-edge provenance (`primary_knowledge_source`) map straight into the same
    two DataFrames, so all traversal/scoring code runs unchanged. Same interface as
    the other backends: download + cache on first use.
    """
    DATA_DIR.mkdir(exist_ok=True)
    nodes_f, edges_f = DATA_DIR / "monarch-kg_nodes.tsv", DATA_DIR / "monarch-kg_edges.tsv"
    if not (nodes_f.exists() and edges_f.exists()):
        tar = DATA_DIR / "monarch-kg.tar.gz"
        if not tar.exists():
            req = urllib.request.Request(MONARCH_URL, headers={"User-Agent": "curl"})
            with net.urlopen_retry(req, timeout=1800) as r, open(tar, "wb") as out:
                shutil.copyfileobj(r, out)
        import tarfile
        with tarfile.open(tar, "r:gz") as t:
            t.extractall(DATA_DIR)

    # Nodes: keep relevant categories; human-restrict genes/proteins (diseases and
    # phenotypes are species-agnostic ontologies). Display name: name -> symbol -> id.
    nodes = pl.read_csv(nodes_f, separator="\t", infer_schema_length=0,
                        columns=["id", "category", "name", "symbol", "in_taxon"])
    nodes = nodes.with_columns(pl.col("category").str.replace("^biolink:", "").alias("cat"))
    keep = nodes.filter(pl.col("cat").is_in(list(_MONARCH_KEEP_CAT)))
    if human_only:
        keep = keep.filter((~pl.col("cat").is_in(["Gene", "Protein"]))
                           | (pl.col("in_taxon") == _MONARCH_HUMAN))
    # phenotypes: keep only human (HPO); drop cross-species ZP/MP/upheno terms
    keep = keep.filter((pl.col("cat") != "PhenotypicFeature")
                       | pl.col("id").str.starts_with("HP:"))
    keep = keep.with_columns(
        pl.coalesce([pl.col("name"), pl.col("symbol"), pl.col("id")]).alias("nm"))
    _G["nodes"] = keep.select([pl.col("id").alias(NODE_ID),
                               pl.col("nm").alias(NODE_NAME),
                               pl.col("cat").alias(NODE_CAT)])
    ids = keep.select(pl.col("id"))

    # Edges: stream, drop negated, keep only edges between kept nodes (semi-joins).
    # Category-filtering the nodes already discards expression/orthology/GO edges,
    # since their other endpoint (Anatomy/BiologicalProcess) is gone.
    edges = (
        pl.scan_csv(edges_f, separator="\t", infer_schema_length=0)
        .select(["subject", "predicate", "object", "primary_knowledge_source", "negated"])
        .filter(pl.col("negated").is_null() | (pl.col("negated").str.to_lowercase() != "true"))
        .filter(~pl.col("predicate").str.replace("^biolink:", "").is_in(list(_MONARCH_DROP_PRED)))
        .join(ids.lazy(), left_on="subject", right_on="id", how="semi")
        .join(ids.lazy(), left_on="object", right_on="id", how="semi")
        .collect(streaming=True))
    _G["edges"] = edges.select([
        pl.col("subject").alias(EDGE_SUBJ),
        pl.col("predicate").str.replace("^biolink:", "").alias(EDGE_PRED),
        pl.col("object").alias(EDGE_OBJ),
        pl.col("primary_knowledge_source").str.replace("^infores:", "")
          .fill_null("monarch").alias(EDGE_SRC)])
    _reset()


def _hgnc_to_entrez() -> dict:
    """HGNC-id -> Entrez-id, from the cached HGNC complete set (gene_norm's download).
    Lets Monarch's HGNC gene ids align with Hetionet's Entrez gene ids."""
    import gene_norm
    gene_norm._load_alias_map()                      # ensure the file is cached
    out = {}
    with gene_norm.CACHE.open(encoding="utf-8") as f:
        col = {n: i for i, n in enumerate(f.readline().rstrip("\n").split("\t"))}
        ih, ie = col.get("hgnc_id"), col.get("entrez_id")
        if ih is None or ie is None:
            return out
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) > max(ih, ie) and p[ih].strip() and p[ie].strip():
                out[p[ih].strip()] = p[ie].strip()
    return out


def _doid_to_mondo() -> dict:
    """DOID -> MONDO id, parsed from Monarch's node xref column (no extra download).
    Lets Hetionet's DOID diseases align onto Monarch's MONDO diseases."""
    f = DATA_DIR / "monarch-kg_nodes.tsv"
    if not f.exists():
        load_monarch()                                # triggers download/extract
    df = (pl.read_csv(f, separator="\t", infer_schema_length=0, columns=["id", "xref"])
          .filter(pl.col("id").str.starts_with("MONDO:") & pl.col("xref").is_not_null()))
    out = {}
    for mid, xref in zip(df["id"].to_list(), df["xref"].to_list()):
        for d in re.findall(r"DOID:\d+", xref or ""):
            out.setdefault(d, mid)                     # first MONDO wins a DOID
    return out


def _drugbank_to_chebi() -> dict:
    """DrugBank-id -> CHEBI id, parsed from Monarch's CHEBI node xref column (no extra
    download). Lets Hetionet's DrugBank compounds align onto Monarch's CHEBI chemicals,
    carrying Hetionet's rich drug edges (treats/binds/regulates) into the merge."""
    f = DATA_DIR / "monarch-kg_nodes.tsv"
    if not f.exists():
        load_monarch()
    df = (pl.read_csv(f, separator="\t", infer_schema_length=0, columns=["id", "xref"])
          .filter(pl.col("id").str.starts_with("CHEBI:") & pl.col("xref").is_not_null()))
    out = {}
    for cid, xref in zip(df["id"].to_list(), df["xref"].to_list()):
        for db in re.findall(r"drugbank:(DB\d+)", xref or "", re.I):
            out.setdefault(db, cid)                    # first CHEBI wins a DrugBank id
    return out


def _apply_id_map(df: "pl.DataFrame", cols: list, mapping: dict) -> "pl.DataFrame":
    """Rewrite id columns through a {old_id -> new_id} map (unmapped ids unchanged)."""
    mdf = pl.DataFrame({"_old": list(mapping.keys()), "_new": list(mapping.values())})
    for c in cols:
        df = (df.join(mdf, left_on=c, right_on="_old", how="left")
                .with_columns(pl.coalesce(["_new", c]).alias(c)).drop("_new"))
    return df


def load_combined() -> None:
    """Merge Hetionet + Monarch into one graph by harmonizing shared entities —
    genes to Entrez, diseases to MONDO — so a disease inherits BOTH Hetionet's
    GWAS-style gene associations AND Monarch's phenotype/PPI edges. A local, honest
    slice of what PrimeKG does (multi-source integration onto common vocabularies).

    Node types that don't share a vocabulary across the two (Hetionet DrugBank
    compounds vs Monarch CHEBI chemicals; Hetionet MeSH symptoms vs Monarch HPO) are
    kept source-prefixed and simply don't cross-link — they still contribute edges.
    """
    load_hetionet(); h_nodes, h_edges = _G["nodes"], _G["edges"]
    load_monarch();  m_nodes, m_edges = _G["nodes"], _G["edges"]

    hgnc, doid2mondo = _hgnc_to_entrez(), _doid_to_mondo()
    drugbank2chebi = _drugbank_to_chebi()

    # Hetionet ids -> canonical: Gene:<entrez> -> NCBIGene:<entrez>; Disease:DOID:x ->
    # MONDO; Compound:DB<x> -> CHEBI (so Hetionet's drug edges join Monarch's chemicals).
    h_map = {}
    for nid in h_nodes[NODE_ID].to_list():
        if nid.startswith("Gene:"):
            h_map[nid] = "NCBIGene:" + nid[5:]
        elif nid.startswith("Disease:"):
            h_map[nid] = doid2mondo.get(nid[len("Disease:"):], nid)
        elif nid.startswith("Compound:") and nid[len("Compound:"):] in drugbank2chebi:
            h_map[nid] = drugbank2chebi[nid[len("Compound:"):]]
    # Monarch ids -> canonical: HGNC:x -> NCBIGene:<entrez> (MONDO/HP/CHEBI stay)
    m_map = {}
    for nid in m_nodes[NODE_ID].to_list():
        if nid.startswith("HGNC:") and nid in hgnc:
            m_map[nid] = "NCBIGene:" + hgnc[nid]

    h_nodes = _apply_id_map(h_nodes, [NODE_ID], h_map)
    m_nodes = _apply_id_map(m_nodes, [NODE_ID], m_map)
    h_edges = _apply_id_map(h_edges, [EDGE_SUBJ, EDGE_OBJ], h_map)
    m_edges = _apply_id_map(m_edges, [EDGE_SUBJ, EDGE_OBJ], m_map)

    # Hetionet first: genes keep Hetionet's symbol names; Monarch-only nodes (MONDO
    # diseases, HPO phenotypes) fill in the rest.
    _G["nodes"] = pl.concat([h_nodes, m_nodes]).unique(subset=[NODE_ID], keep="first")
    _G["edges"] = pl.concat([h_edges, m_edges])
    _reset()


def load_ml_demo() -> None:
    """A tiny FUSED biomedical<->ML graph (ml_schema.seed_fused_demo): the method layer
    (authorship, lineage, benchmark-vs-stable trust) plugged into the same traversal code,
    bridged to a disease via DataModality. KG_BACKEND=ml_demo."""
    import ml_schema
    nodes, edges = ml_schema.seed_fused_demo()
    _G["nodes"] = pl.DataFrame({NODE_ID: [n[0] for n in nodes],
                                NODE_NAME: [n[1] for n in nodes],
                                NODE_CAT: [n[2] for n in nodes]})
    _G["edges"] = pl.DataFrame({EDGE_SUBJ: [e[0] for e in edges],
                                EDGE_PRED: [e[1] for e in edges],
                                EDGE_OBJ: [e[2] for e in edges],
                                EDGE_SRC: [e[3] for e in edges]})
    _reset()


def load_ml() -> None:
    """The REAL fused ML+biomedical seed (seeds/ml_fused.json, built by ml_seed.py): real
    arXiv authorship/dates, curated lineage + reified benchmarks + biomedical bridge."""
    import ml_schema
    nodes, edges = ml_schema.load_fused_seed()
    _G["nodes"] = pl.DataFrame({NODE_ID: [n[0] for n in nodes],
                                NODE_NAME: [n[1] for n in nodes],
                                NODE_CAT: [n[2] for n in nodes]})
    _G["edges"] = pl.DataFrame({EDGE_SUBJ: [e[0] for e in edges],
                                EDGE_PRED: [e[1] for e in edges],
                                EDGE_OBJ: [e[2] for e in edges],
                                EDGE_SRC: [e[3] for e in edges]})
    _reset()


_BACKENDS = {"demo": load_demo, "hetionet": load_hetionet, "monarch": load_monarch,
             "combined": load_combined, "ml_demo": load_ml_demo, "ml": load_ml,
             "optimuskg": load_optimuskg}


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


# When a name collides across categories (e.g. 'Alzheimer disease' exists as both a
# Disease and an HPO PhenotypicFeature), prefer the entity type that matters for
# mechanism hypotheses. Lower rank = preferred.
_CAT_RANK = {"disease": 0, "gene": 1, "drug": 1, "compound": 1, "protein": 2,
             "chemicalentity": 2, "pathway": 3, "anatomy": 4,
             "phenotypicfeature": 5, "phenotype": 5, "symptom": 5}


def _rank(cat: str) -> int:
    return _CAT_RANK.get(cat.lower().replace("biolink:", ""), 3)


def _best(cands: list) -> str | None:
    """Pick the best candidate id by (category preference, then shortest name)."""
    meta = _meta()
    return min(cands, key=lambda nid: (_rank(meta[nid][1]), len(meta[nid][0]))) if cands else None


def _resolve(name: str) -> str | None:
    """Map free-text to a node id (exact id, exact name, then substring).

    On collisions, prefer the more hypothesis-relevant type (Disease/Gene over
    Phenotype) so 'Alzheimer disease' resolves to the disease, not the HPO term."""
    meta = _meta()
    if name in meta:
        return name
    low = name.lower()
    exact = [nid for nid, (nm, _) in meta.items() if nm.lower() == low]
    if exact:
        return _best(exact)
    sub = [nid for nid, (nm, _) in meta.items() if low in nm.lower()]
    return _best(sub)


def _label(node_id: str) -> str:
    nm, cat = _meta().get(node_id, (node_id, "?"))
    return f"{nm} ({cat})"


# --------------------------------------------------------------------------- #
# Entity normalization — map a free-text string to a canonical KG node, so the #
# curated KG dedups surface variants ('ulcerative colitis (UC)' -> the node)   #
# and unresolvable junk ('CID11879209') is flagged rather than stored as fact. #
# --------------------------------------------------------------------------- #

def _clean(s: str) -> str:
    """Lowercase, drop parentheticals, keep alphanumerics — for loose matching."""
    s = re.sub(r"\(.*?\)", " ", s.lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _norm_index() -> dict:
    global _NORM
    if _NORM is None:
        meta = _meta()          # force the load FIRST (it may _reset() _NORM), THEN build
        idx = {}                # into a local so a cold-start reset can't clobber it
        for nid, (nm, _) in meta.items():
            idx.setdefault(_clean(nm), nid)     # first node wins a cleaned name
        _NORM = idx
    return _NORM


def normalize_entity(name: str) -> dict | None:
    """Resolve a free-text entity to a canonical node {id, name, category}, or None.

    TYPE-AWARE cascade: each entity class gets the tool that's actually good at it.
      1. GENES  -> curated HGNC alias table (gene_norm): 'IL8' -> CXCL8 exactly.
      2. REST   -> semantic embeddings (entity_norm, if ENTITY_NORM=semantic) for
                   disease/clinical synonyms ('heart attack' -> MI), else lexical.
    None means "no confident match in this KG" — NOT "invalid" (closed-world);
    callers keep the raw string, they don't drop it. Each step degrades gracefully.
    """
    try:                                          # 1. gene dictionary (best for symbols)
        import gene_norm
        g = gene_norm.normalize_gene(name)
        if g is not None:
            return g
    except Exception as err:
        print(f"[gene_norm unavailable: {err}; skipping gene step]")

    if os.environ.get("ENTITY_NORM", "lexical").lower() == "semantic":  # 2a. semantic
        try:
            import entity_norm
            hit = entity_norm.normalize(name)
            if hit is not None:
                return hit
        except Exception as err:
            print(f"[entity_norm semantic unavailable: {err}; using lexical]")
    return _normalize_lexical(name)               # 2b. lexical fallback


def _normalize_lexical(name: str) -> dict | None:
    q = _clean(name)
    if len(q) < 2:
        return None
    idx = _norm_index()
    nid = idx.get(q)
    if nid is None:                              # longest node-name phrase inside the query
        padded_q = f" {q} "
        best = None
        for cname, cid in idx.items():
            if len(cname) >= 4 and f" {cname} " in padded_q:
                if best is None or len(cname) > len(best[0]):
                    best = (cname, cid)
        nid = best[1] if best else None
    if nid is None:
        return None
    nm, cat = _meta()[nid]
    return {"id": nid, "name": nm, "category": cat}


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


def enumerate_paths(entity_a: str, entity_c: str, max_len: int = 3,
                    max_paths: int = 20, max_expand: int = 60000) -> tuple:
    """Resolve two entities and return connecting paths (bounded BFS).

    Returns (a_id, c_id, paths, truncated). Each path is a list of
    (from_id, predicate, arrow, source, to_id). a_id/c_id are None if unresolved.
    Shared by find_paths (display) and hypothesis.py (scoring) so both see the
    same paths. Bounded so a dense real graph can't blow up.
    """
    a, c = _resolve(entity_a), _resolve(entity_c)
    if a is None or c is None:
        return a, c, [], False

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

    paths.sort(key=len)
    return a, c, paths, truncated


def find_paths(entity_a: str, entity_c: str, max_len: int = 3) -> str:
    """Find connecting paths A..C — the A->B->C discovery move."""
    a, c, paths, truncated = enumerate_paths(entity_a, entity_c, max_len=max_len)
    if a is None or c is None:
        missing = entity_a if a is None else entity_c
        return f"'{missing}' not found in the knowledge graph."
    if not paths:
        note = " (search truncated)" if truncated else ""
        return f"No path between {_label(a)} and {_label(c)} within {max_len} hops{note}."

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


# Sources whose edges are low-trust corroboration (mere co-occurrence / text-mined
# / computational). A path leaning on these is only "weakly grounded".
_LOW_TRUST = ("cooccurrence", "co-occurrence", "text", "predicted", "stargeo",
              "lincs", "string",   # STRING PPIs include predicted/text-mined links
              "benchmark", "leaderboard", "sota")   # ML: benchmark-relative + non-stationary


def _trustworthy(source: str) -> bool:
    s = source.lower()
    return not any(k in s for k in _LOW_TRUST)


def check_connection(entity_a: str, entity_c: str, max_len: int = 3) -> str:
    """Grade how well a TRUSTWORTHY KG subgraph corroborates a claimed link.

    IMPORTANT: absence of KG support does NOT mean the hypothesis is false — the
    KG is incomplete (closed-world). A claim is well-grounded only when the
    reasoning traverses a MAJORITY-TRUSTWORTHY path; otherwise it is novel /
    uncorroborated and should be VERIFIED, not discarded.

    Returns: 'grounded' | 'weakly_grounded' | 'novel_unverified' | 'off_graph'.
    """
    a, c, paths, _ = enumerate_paths(entity_a, entity_c, max_len=max_len)
    if a is None or c is None:
        return "off_graph"            # entity absent from this KG — can't assess
    if not paths:
        return "novel_unverified"     # entities exist but no path — possibly novel
    for p in paths:                   # shortest-first
        majority_trust = sum(_trustworthy(src) for (_, _, _, src, _) in p) * 2 > len(p)
        if len(p) <= 2 and majority_trust:      # short AND trustworthy = real grounding
            return "grounded"
    return "weakly_grounded"          # only long or low-trust paths — tenuous, not strong
