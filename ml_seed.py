"""ml_seed — build the REAL fused-ML seed and cache it to seeds/ml_fused.json.

Authorship + year + title are fetched LIVE from the arXiv API (real, verifiable). Lineage
(derived_from / superseded_by), labs, reified benchmark results, and the biomedical bridge
are hand-curated from public knowledge (arXiv gives neither affiliations nor benchmark
numbers). Benchmark values are representative public figures and are LOW-trust by design.

Run once to (re)generate the committed seed:  python ml_seed.py
Loaders (ml_schema.load_fused_seed / kg_memory load_ml) just read the cached JSON.
"""

import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import ml_schema

SEED = Path(__file__).parent / "seeds" / "ml_fused.json"
_NS = {"a": "http://www.w3.org/2005/Atom"}

# name -> (arxiv id, category, derived_from, superseded_by, lab[hand-curated])
CURATED = {
    "Transformer": ("1706.03762", "Architecture", [], "", "Google Brain"),
    "BERT":        ("1810.04805", "Model", ["Transformer"], "RoBERTa", "Google"),
    "RoBERTa":     ("1907.11692", "Model", ["BERT"], "", "FAIR / UW"),
    "GPT-3":       ("2005.14165", "Model", ["Transformer"], "", "OpenAI"),
    "ViT":         ("2010.11929", "Architecture", ["Transformer"], "", "Google"),
    "ResNet":      ("1512.03385", "Architecture", [], "", "Microsoft Research"),
    "U-Net":       ("1505.04597", "Architecture", [], "", "U Freiburg"),
    "GCN":         ("1609.02907", "Architecture", [], "", "U Amsterdam"),
    "GAN":         ("1406.2661", "Architecture", [], "", "U Montreal"),
    "VAE":         ("1312.6114", "Architecture", [], "", "U Amsterdam"),
    "Adam":        ("1412.6980", "Method", [], "", "U Amsterdam / Toronto"),
    "BatchNorm":   ("1502.03167", "Method", [], "", "Google"),
    "DDPM":        ("2006.11239", "Architecture", [], "", "UC Berkeley"),
}

# reified benchmark results — representative PUBLIC figures (low-trust by design)
BENCHMARKS = [
    ml_schema.BenchmarkResult("BERT", "GLUE", "avg", 80.5, 2018, True, "Devlin 2018"),
    ml_schema.BenchmarkResult("RoBERTa", "GLUE", "avg", 88.5, 2019, True, "Liu 2019"),
    ml_schema.BenchmarkResult("ResNet", "ImageNet", "top-1", 78.3, 2015, True, "He 2015 (ResNet-152)"),
    ml_schema.BenchmarkResult("ViT", "ImageNet", "top-1", 88.5, 2020, True, "Dosovitskiy 2020 (ViT-L/16, JFT)"),
]

# hand-curated biomedical<->ML bridge (domain knowledge)
BRIDGE_NODES = [
    ("MONDO:AF", "atrial fibrillation", "Disease"),
    ("MONDO:t2d", "type 2 diabetes mellitus", "Disease"),
    ("MODALITY:ECG", "ECG (12-lead)", "DataModality"),
    ("MODALITY:imaging", "medical imaging", "DataModality"),
    ("MODALITY:genomic", "genomic sequence", "DataModality"),
    ("MODALITY:ehr", "tabular EHR", "DataModality"),
    ("TASK:seq-clf", "sequence classification", "Task"),
    ("TASK:seg", "segmentation", "Task"),
    ("TASK:survival", "time-to-event / survival", "Task"),
    ("LOSS:focal", "focal loss", "Loss"),
    ("LOSS:coxpl", "Cox partial likelihood", "Loss"),
    ("METRIC:auroc", "AUROC", "Metric"),
    ("METRIC:cindex", "C-index", "Metric"),
]
BRIDGE_EDGES = [
    ("MONDO:AF", "manifests_in", "MODALITY:ECG", "clinical knowledge"),
    ("MONDO:t2d", "manifests_in", "MODALITY:ehr", "clinical knowledge"),
    ("METHOD:Transformer", "suited_to", "MODALITY:ECG", "methodological"),
    ("METHOD:ResNet", "suited_to", "MODALITY:imaging", "methodological"),
    ("METHOD:ViT", "suited_to", "MODALITY:imaging", "methodological"),
    ("METHOD:U-Net", "suited_to", "MODALITY:imaging", "methodological"),
    ("METHOD:GCN", "suited_to", "MODALITY:genomic", "methodological"),
    ("METHOD:Transformer", "used_for", "TASK:seq-clf", "methodological"),
    ("METHOD:U-Net", "used_for", "TASK:seg", "methodological"),
    ("METHOD:Transformer", "trained_with", "LOSS:focal", "methodological"),
    ("TASK:seq-clf", "evaluated_by", "METRIC:auroc", "methodological"),
    ("TASK:survival", "evaluated_by", "METRIC:cindex", "methodological"),
    ("TASK:survival", "trained_with", "LOSS:coxpl", "methodological"),
]


def _fetch_arxiv(ids: list) -> dict:
    """Real first/last author, year, title per arXiv id (batched)."""
    url = ("http://export.arxiv.org/api/query?id_list=" + ",".join(ids)
           + f"&max_results={len(ids)}")
    root = ET.fromstring(urllib.request.urlopen(url, timeout=60).read())
    out = {}
    for e in root.findall("a:entry", _NS):
        aid = e.findtext("a:id", "", _NS).split("/abs/")[-1].split("v")[0]
        authors = [a.findtext("a:name", "", _NS) for a in e.findall("a:author", _NS)]
        out[aid] = {"first": authors[0] if authors else "",
                    "last": authors[-1] if len(authors) > 1 else "",
                    "n_authors": len(authors),
                    "year": int(e.findtext("a:published", "0", _NS)[:4] or 0) or None,
                    "title": " ".join(e.findtext("a:title", "", _NS).split())}
    return out


def build() -> Path:
    meta = _fetch_arxiv([v[0] for v in CURATED.values()])
    methods = []
    for name, (arxiv, cat, parents, superseded, lab) in CURATED.items():
        m = meta.get(arxiv, {})
        methods.append(ml_schema.Method(
            name=name, category=cat, year=m.get("year"),
            first_author=m.get("first", ""), last_author=m.get("last", ""),
            lab=lab, intro_paper=f"arXiv:{arxiv}",
            derived_from=parents, superseded_by=superseded))
    nodes, edges = ml_schema.fused_rows(methods, BENCHMARKS, BRIDGE_NODES, BRIDGE_EDGES)
    SEED.parent.mkdir(parents=True, exist_ok=True)
    SEED.write_text(json.dumps({"nodes": nodes, "edges": edges,
                                "n_methods": len(methods), "n_benchmarks": len(BENCHMARKS)},
                               indent=2), encoding="utf-8")
    return SEED


if __name__ == "__main__":
    p = build()
    d = json.loads(p.read_text())
    print(f"Wrote {p} — {len(d['nodes'])} nodes / {len(d['edges'])} edges "
          f"({d['n_methods']} methods w/ real arXiv authorship, {d['n_benchmarks']} benchmarks)")
