"""ml_seed — build the REAL fused-ML seed and cache it to seeds/ml_fused.json.

Authorship + year + title are fetched LIVE from the arXiv API (real, verifiable). Lineage
(derived_from / superseded_by), labs, reified benchmark results, and the biomedical bridge
are hand-curated from public knowledge (arXiv gives neither affiliations nor benchmark
numbers). Benchmark values are representative public figures and are LOW-trust by design.

Run once to (re)generate the committed seed:  python ml_seed.py
Loaders (ml_schema.load_fused_seed / kg_memory load_ml) just read the cached JSON.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import ml_schema
import net

SEED = Path(__file__).parent / "seeds" / "ml_fused.json"
_NS = {"a": "http://www.w3.org/2005/Atom"}

# name -> (arxiv id, category, derived_from, superseded_by, lab[hand], title_must_contain).
# title_must_contain is a GUARD: after fetching, we verify the real arXiv title contains
# this substring (case-insensitive), so a mistyped id can't silently attribute the wrong
# paper's authors — mismatches are dropped + reported.
CURATED = {
    # --- seq / attention foundations ---
    "Seq2Seq":     ("1409.3215", "Architecture", [], "", "Google", "Sequence to Sequence"),
    "Bahdanau-Attention": ("1409.0473", "Method", [], "", "Montreal", "Jointly Learning to Align"),
    "GRU":         ("1406.1078", "Architecture", [], "", "Montreal", "RNN Encoder"),
    "Word2Vec":    ("1301.3781", "Method", [], "", "Google", "Efficient Estimation"),
    "Transformer": ("1706.03762", "Architecture", ["Seq2Seq", "Bahdanau-Attention"], "", "Google Brain", "Attention Is All You Need"),
    # --- transformers / LLMs ---
    "BERT":        ("1810.04805", "Model", ["Transformer"], "RoBERTa", "Google", "BERT"),
    "RoBERTa":     ("1907.11692", "Model", ["BERT"], "", "FAIR / UW", "Robustly Optimized"),
    "ALBERT":      ("1909.11942", "Model", ["BERT"], "", "Google", "ALBERT"),
    "DistilBERT":  ("1910.01108", "Model", ["BERT"], "", "Hugging Face", "DistilBERT"),
    "ELECTRA":     ("2003.10555", "Model", ["BERT"], "", "Stanford / Google", "ELECTRA"),
    "XLNet":       ("1906.08237", "Model", ["Transformer"], "", "CMU / Google", "XLNet"),
    "T5":          ("1910.10683", "Model", ["Transformer"], "", "Google", "Transfer Learning"),
    "BART":        ("1910.13461", "Model", ["Transformer"], "", "FAIR", "BART"),
    "ELMo":        ("1802.05365", "Model", [], "", "Allen AI", "Deep contextualized"),
    "GPT-3":       ("2005.14165", "Model", ["Transformer"], "", "OpenAI", "Few-Shot Learners"),
    "InstructGPT": ("2203.02155", "Model", ["GPT-3"], "", "OpenAI", "human feedback"),
    "LLaMA":       ("2302.13971", "Model", ["Transformer"], "", "Meta", "LLaMA"),
    "PaLM":        ("2204.02311", "Model", ["Transformer"], "", "Google", "PaLM"),
    "Chinchilla":  ("2203.15556", "Model", ["Transformer"], "", "DeepMind", "Compute-Optimal"),
    # --- CV backbones / detection / segmentation ---
    "VGG":         ("1409.1556", "Architecture", [], "", "Oxford VGG", "Very Deep Convolutional"),
    "GoogLeNet":   ("1409.4842", "Architecture", [], "", "Google", "Going Deeper"),
    "ResNet":      ("1512.03385", "Architecture", [], "DenseNet", "Microsoft Research", "Deep Residual"),
    "DenseNet":    ("1608.06993", "Architecture", ["ResNet"], "", "Cornell / Tsinghua", "Densely Connected"),
    "MobileNet":   ("1704.04861", "Architecture", [], "", "Google", "MobileNets"),
    "EfficientNet":("1905.11946", "Architecture", [], "", "Google", "EfficientNet"),
    "U-Net":       ("1505.04597", "Architecture", [], "", "U Freiburg", "U-Net"),
    "Faster-RCNN": ("1506.01497", "Architecture", [], "Mask-RCNN", "Microsoft Research", "Faster R-CNN"),
    "YOLO":        ("1506.02640", "Architecture", [], "", "UW / FAIR", "You Only Look Once"),
    "Mask-RCNN":   ("1703.06870", "Architecture", ["Faster-RCNN"], "", "FAIR", "Mask R-CNN"),
    "ViT":         ("2010.11929", "Architecture", ["Transformer"], "", "Google", "16x16 Words"),
    "Swin":        ("2103.14030", "Architecture", ["ViT"], "", "Microsoft Research", "Swin Transformer"),
    "ConvNeXt":    ("2201.03545", "Architecture", ["ResNet"], "", "FAIR", "2020s"),
    # --- generative ---
    "GAN":         ("1406.2661", "Architecture", [], "", "U Montreal", "Generative Adversarial"),
    "DCGAN":       ("1511.06434", "Architecture", ["GAN"], "", "indico / FAIR", "Deep Convolutional Generative"),
    "WGAN":        ("1701.07875", "Architecture", ["GAN"], "", "Courant / FAIR", "Wasserstein"),
    "StyleGAN":    ("1812.04948", "Architecture", ["GAN"], "", "NVIDIA", "Style-Based Generator"),
    "CycleGAN":    ("1703.10593", "Architecture", ["GAN"], "", "Berkeley", "Unpaired Image-to-Image"),
    "VAE":         ("1312.6114", "Architecture", [], "", "U Amsterdam", "Auto-Encoding Variational"),
    "DDPM":        ("2006.11239", "Architecture", [], "", "UC Berkeley", "Denoising Diffusion"),
    "LatentDiffusion": ("2112.10752", "Architecture", ["DDPM"], "", "LMU Munich", "Latent Diffusion"),
    # --- self-supervised / multimodal ---
    "SimCLR":      ("2002.05709", "Method", [], "", "Google", "Contrastive Learning"),
    "MoCo":        ("1911.05722", "Method", [], "", "FAIR", "Momentum Contrast"),
    "BYOL":        ("2006.07733", "Method", [], "", "DeepMind", "Bootstrap Your Own Latent"),
    "MAE":         ("2111.06377", "Method", ["ViT"], "", "FAIR", "Masked Autoencoders"),
    "CLIP":        ("2103.00020", "Model", [], "", "OpenAI", "Transferable Visual Models"),
    # --- graph ---
    "GCN":         ("1609.02907", "Architecture", [], "", "U Amsterdam", "Graph Convolutional"),
    "GraphSAGE":   ("1706.02216", "Architecture", ["GCN"], "", "Stanford", "Inductive Representation"),
    "GAT":         ("1710.10903", "Architecture", ["GCN"], "", "Cambridge / Montreal", "Graph Attention"),
    "Node2Vec":    ("1607.00653", "Method", [], "", "Stanford", "node2vec"),
    # --- classical / tabular (still SOTA for tabular EHR) ---
    "XGBoost":     ("1603.02754", "Method", [], "", "U Washington", "Scalable Tree Boosting"),
    # --- optimization / normalization ---
    "Adam":        ("1412.6980", "Method", [], "", "U Amsterdam / Toronto", "Adam"),
    "BatchNorm":   ("1502.03167", "Method", [], "", "Google", "Batch Normalization"),
    "LayerNorm":   ("1607.06450", "Method", [], "", "Toronto", "Layer Normalization"),
    "Dropout":     ("1207.0580", "Method", [], "", "Toronto", "co-adaptation"),
    # --- reinforcement learning ---
    "DQN":         ("1312.5602", "Model", [], "", "DeepMind", "Playing Atari"),
    "A3C":         ("1602.01783", "Method", [], "", "DeepMind", "Asynchronous Methods"),
    "TRPO":        ("1502.05477", "Method", [], "PPO", "Berkeley", "Trust Region"),
    "PPO":         ("1707.06347", "Method", ["TRPO"], "", "OpenAI", "Proximal Policy Optimization"),
    "DDPG":        ("1509.02971", "Method", [], "", "DeepMind", "Continuous Control"),
    "SAC":         ("1801.01290", "Method", [], "", "Berkeley", "Soft Actor-Critic"),
    "AlphaZero":   ("1712.01815", "Model", [], "", "DeepMind", "General Reinforcement"),
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
    # EHR is TWO data structures, and the structure determines the architecture:
    ("MODALITY:ehr-events", "longitudinal event-based EHR (event streams)", "DataModality"),
    ("MODALITY:ehr-tabular", "aggregated tabular EHR (per-encounter feature vectors)", "DataModality"),
    # encoding standards for the event-based form, and source datasets realizable as either
    ("STD:omop", "OMOP-CDM", "DataStandard"),
    ("STD:meds", "MEDS (Medical Event Data Standard)", "DataStandard"),
    ("DATASET:mimic", "MIMIC-IV", "Dataset"),
    ("DATASET:eicu", "eICU", "Dataset"),
    ("CAVEAT:irregular", "irregular sampling / variable-length sequences", "Caveat"),
    ("CAVEAT:aggloss", "information loss from aggregation", "Caveat"),
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
    ("MONDO:t2d", "studied_via", "MODALITY:ehr-events", "clinical knowledge"),
    ("MONDO:t2d", "studied_via", "MODALITY:ehr-tabular", "clinical knowledge"),
    # standards encode the event-based structure; source datasets realize either form
    ("STD:omop", "encodes", "MODALITY:ehr-events", "OHDSI"),
    ("STD:meds", "encodes", "MODALITY:ehr-events", "MEDS"),
    ("DATASET:mimic", "conforms_to", "STD:omop", "MIMIC-IV OMOP release"),
    ("DATASET:mimic", "available_as", "MODALITY:ehr-events", "event-level source"),
    ("DATASET:mimic", "available_as", "MODALITY:ehr-tabular", "commonly flattened for ML"),
    ("DATASET:eicu", "available_as", "MODALITY:ehr-events", "event-level source"),
    ("DATASET:eicu", "available_as", "MODALITY:ehr-tabular", "commonly flattened for ML"),
    ("MODALITY:ehr-events", "has_caveat", "CAVEAT:irregular", "clinical ML"),
    ("MODALITY:ehr-tabular", "has_caveat", "CAVEAT:aggloss", "clinical ML"),
    # architectures route by STRUCTURE: sequence models to events, GBDT to tabular
    ("METHOD:Transformer", "suited_to", "MODALITY:ehr-events", "methodological"),
    ("METHOD:GRU", "suited_to", "MODALITY:ehr-events", "methodological"),
    ("METHOD:XGBoost", "suited_to", "MODALITY:ehr-tabular", "methodological"),
    ("METHOD:XGBoost", "used_for", "TASK:survival", "methodological"),
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


def _fetch_arxiv(ids: list, batch: int = 25) -> dict:
    """Real first/last author, year, title per arXiv id — batched + polite (arXiv asks
    ~3s between requests)."""
    import time
    out = {}
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        url = ("http://export.arxiv.org/api/query?id_list=" + ",".join(chunk)
               + f"&max_results={len(chunk)}")
        root = ET.fromstring(net.fetch_bytes(url, timeout=90))
        for e in root.findall("a:entry", _NS):
            aid = e.findtext("a:id", "", _NS).split("/abs/")[-1].split("v")[0]
            authors = [a.findtext("a:name", "", _NS) for a in e.findall("a:author", _NS)]
            out[aid] = {"first": authors[0] if authors else "",
                        "last": authors[-1] if len(authors) > 1 else "",
                        "n_authors": len(authors),
                        "year": int(e.findtext("a:published", "0", _NS)[:4] or 0) or None,
                        "title": " ".join(e.findtext("a:title", "", _NS).split())}
        if i + batch < len(ids):
            time.sleep(3)
    return out


def build() -> Path:
    meta = _fetch_arxiv([v[0] for v in CURATED.values()])
    methods, dropped = [], []
    for name, (arxiv, cat, parents, superseded, lab, title_kw) in CURATED.items():
        m = meta.get(arxiv)
        # GUARD: the fetched title must contain the expected keyword, else the id is wrong
        # and we'd attribute the wrong paper's authors — drop + report.
        if not m or title_kw.lower() not in m.get("title", "").lower():
            dropped.append((name, arxiv, (m or {}).get("title", "(not resolved)")))
            continue
        methods.append(ml_schema.Method(
            name=name, category=cat, year=m.get("year"),
            first_author=m.get("first", ""), last_author=m.get("last", ""),
            lab=lab, intro_paper=f"arXiv:{arxiv}",
            derived_from=parents, superseded_by=superseded))
    if dropped:
        print(f"[dropped {len(dropped)} on title-guard mismatch — fix the arXiv id]:")
        for name, aid, title in dropped:
            print(f"    {name} (arXiv:{aid}) -> fetched: {title[:70]!r}")
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
