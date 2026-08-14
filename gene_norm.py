"""gene_norm — gene-symbol aliasing via the curated HGNC table (not a model).

Gene symbols are identifiers with official synonym registries, so a dictionary
beats any embedding: HGNC lists each gene's approved symbol plus its previous and
alias symbols. 'IL8' is HGNC's *previous symbol* for CXCL8 — a lookup gets that
exactly right, where BioLORD gave 'IL16'.

resolve_symbol() maps any symbol/alias/previous-symbol to the approved symbol;
normalize_gene() then finds that approved symbol as a Gene node in the loaded KG.
The HGNC table (~17MB TSV) is downloaded and cached on first use.
"""

import shutil
import urllib.request
from pathlib import Path

import net

HGNC_URL = ("https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/"
            "hgnc_complete_set.txt")
CACHE = Path(__file__).parent / "data" / "hgnc_complete_set.txt"

_ALIAS = None      # UPPER(symbol|alias|prev) -> approved symbol
_GENE_NODES = None # UPPER(gene node name) -> {id, name, category}


def _load_alias_map() -> dict:
    """Build UPPER(any symbol form) -> approved symbol from the HGNC complete set."""
    global _ALIAS
    if _ALIAS is not None:
        return _ALIAS
    if not CACHE.exists():
        CACHE.parent.mkdir(exist_ok=True)
        req = urllib.request.Request(HGNC_URL, headers={"User-Agent": "curl"})
        with net.urlopen_retry(req, timeout=120) as r, open(CACHE, "wb") as out:
            shutil.copyfileobj(r, out)

    with CACHE.open(encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        col = {name: i for i, name in enumerate(header)}
        i_sym, i_alias, i_prev = col["symbol"], col["alias_symbol"], col["prev_symbol"]

        amap: dict = {}
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= i_prev:
                continue
            sym = parts[i_sym].strip()
            if not sym:
                continue
            amap[sym.upper()] = sym
            for field in (parts[i_alias], parts[i_prev]):
                for alt in field.strip('"').split("|"):
                    alt = alt.strip()
                    if alt:
                        amap.setdefault(alt.upper(), sym)   # approved symbol wins ties
    _ALIAS = amap
    return _ALIAS


def _gene_node_index() -> dict:
    global _GENE_NODES
    if _GENE_NODES is None:
        import kg_memory as kg
        idx = {}
        for nid, (nm, cat) in kg._meta().items():
            if cat.lower() == "gene":
                idx.setdefault(nm.upper(), {"id": nid, "name": nm, "category": cat})
        _GENE_NODES = idx
    return _GENE_NODES


def resolve_symbol(mention: str) -> str | None:
    """Map a gene symbol / alias / previous symbol to its HGNC approved symbol."""
    m = mention.strip().upper()
    return _load_alias_map().get(m) if m else None


def normalize_gene(mention: str) -> dict | None:
    """Resolve a gene mention to a canonical Gene node in the loaded KG, or None.

    None means 'not a known gene symbol/alias, or that gene isn't in this KG' —
    NOT 'invalid'. Callers fall through to disease/semantic normalization.
    """
    approved = resolve_symbol(mention)
    if approved is None:
        return None
    return _gene_node_index().get(approved.upper())
