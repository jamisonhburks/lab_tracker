"""Semantic entity normalization — map a mention to a canonical KG node by MEANING.

The lexical matcher in kg_memory.normalize_entity handles surface variants
('ulcerative colitis (UC)') but misses true synonymy ('heart attack' vs
'myocardial infarction'). This module catches those with a biomedical sentence
embedding model (BioLORD-2023 by default) — the same embed + cosine nearest-
neighbor pattern as semantic memory, applied to entity → concept linking.

CAVEAT (measured): BioLORD excels at disease/phenotype/clinical concepts
(heart attack -> Myocardial infarction 0.79; 'Crohn disease' -> "Crohn's disease"
0.99) but is UNRELIABLE for GENE SYMBOLS — it maps 'IL8' -> 'IL16' at 0.95
(surface shape, not gene identity). Gene-symbol aliasing needs a curated alias
table (HGNC / NCBI Gene), not an embedding model — a type-aware normalizer
(dictionary for genes, semantic for diseases) is the proper next step.

Opt-in and lazy: nothing loads until first use, and kg_memory only routes here
when ENTITY_NORM=semantic. All node-name embeddings are built once and cached to
disk, so subsequent runs are fast.

  ENTITY_NORM_MODEL      HF model id (default FremyCompany/BioLORD-2023)
  ENTITY_NORM_THRESHOLD  min cosine to accept a match (default 0.60)
"""

import hashlib
import os
from pathlib import Path

import numpy as np

import kg_memory as kg

MODEL_NAME = os.environ.get("ENTITY_NORM_MODEL", "FremyCompany/BioLORD-2023")
THRESHOLD = float(os.environ.get("ENTITY_NORM_THRESHOLD", "0.60"))
CACHE_DIR = Path(__file__).parent / "data"

_model = None
_index = None   # {"ids", "names", "cats", "vecs"}


def _device() -> str:
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME, device=_device())
    return _model


def _build_index() -> dict:
    """Embed every KG node name once (cached to disk), for nearest-neighbor lookup."""
    global _index
    if _index is not None:
        return _index

    meta = kg._meta()                       # id -> (name, category)
    ids = list(meta.keys())
    names = [meta[i][0] for i in ids]
    cats = [meta[i][1] for i in ids]

    backend = os.environ.get("KG_BACKEND", "demo")
    key = hashlib.md5(f"{MODEL_NAME}|{backend}|{len(ids)}".encode()).hexdigest()[:12]
    cache = CACHE_DIR / f"entnorm_{key}.npy"

    if cache.exists():
        vecs = np.load(cache)
    else:
        CACHE_DIR.mkdir(exist_ok=True)
        vecs = _load_model().encode(
            names, batch_size=256, convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False)
        np.save(cache, vecs)

    _index = {"ids": ids, "names": names, "cats": cats, "vecs": vecs}
    return _index


def normalize(name: str, threshold: float | None = None) -> dict | None:
    """Nearest canonical node to `name` by embedding cosine, or None below threshold.

    None means 'no confident concept match' — NOT 'invalid' (closed-world): the
    caller keeps the raw string rather than forcing a bad link.
    """
    if not name or not name.strip():
        return None
    thr = THRESHOLD if threshold is None else threshold
    idx = _build_index()
    q = _load_model().encode([name], convert_to_numpy=True, normalize_embeddings=True)[0]
    sims = idx["vecs"] @ q                   # both L2-normalized -> cosine
    i = int(np.argmax(sims))
    if sims[i] < thr:
        return None
    return {"id": idx["ids"][i], "name": idx["names"][i],
            "category": idx["cats"][i], "score": round(float(sims[i]), 3)}
