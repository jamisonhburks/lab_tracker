"""Semantic memory: decontextualized facts, recalled by MEANING.

Semantic = "what is true", stripped of the episode it came from. Each fact is
stored with its provenance and a local embedding (nomic-embed-text via Ollama).

Recall is a small retrieval stack, not a single scorer:
  1. DENSE   — cosine similarity of embeddings (catches paraphrase).
  2. SPARSE  — BM25 over the raw text (catches exact terms: gene names, PMIDs).
  3. FUSE    — Reciprocal Rank Fusion combines the two rankings (hybrid).
  4. THRESHOLD — drop anything below MIN_SIM so we never ground on noise.
  5. MMR     — pick the final k trading relevance against diversity, so we
               don't return five near-duplicate facts.

The interface (add_fact / search_semantic) mirrors episodic memory so the agent
loop treats them the same way.
"""

import json
import math
import re
from pathlib import Path

import numpy as np
import ollama

import store_lock

STORE = Path(__file__).parent / "memory" / "semantic.jsonl"
EMBED_MODEL = "nomic-embed-text"

MIN_SIM = 0.55      # similarity floor — facts below this are treated as irrelevant
MMR_LAMBDA = 0.7    # 1.0 = pure relevance, 0.0 = pure diversity
RRF_K = 60          # Reciprocal Rank Fusion constant (standard default)


def _embed(text: str) -> list:
    return ollama.embed(model=EMBED_MODEL, input=text)["embeddings"][0]


def _tok(text: str) -> list:
    return re.findall(r"[a-z0-9]+", text.lower())   # tokens WITH repetition (for tf)


def _cos(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _load() -> list:
    if not STORE.exists():
        return []
    with STORE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def add_fact(claim: str, sources: list) -> dict | None:
    """Store one fact with provenance + embedding. Deduplicates on exact text."""
    STORE.parent.mkdir(parents=True, exist_ok=True)
    if any(r["text"] == claim for r in _load()):
        return None  # already known — consolidation shouldn't duplicate
    record = {"text": claim, "sources": sources, "vector": _embed(claim)}
    store_lock.append_jsonl(STORE, record)     # locked append — safe across concurrent sessions
    return record


# --------------------------------------------------------------------------- #
# Scorers                                                                      #
# --------------------------------------------------------------------------- #

def _bm25_scores(query: str, docs: list, k1: float = 1.5, b: float = 0.75) -> list:
    """Classic BM25: rare shared terms score high, with length normalization."""
    corpus = [_tok(d) for d in docs]
    n = len(corpus)
    avgdl = sum(len(d) for d in corpus) / n if n else 0.0

    df = {}
    for toks in corpus:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1

    q_terms = set(_tok(query))
    scores = []
    for toks in corpus:
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        dl = len(toks)
        s = 0.0
        for t in q_terms:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
        scores.append(s)
    return scores


def _rrf(*rankings, k: int = RRF_K) -> dict:
    """Reciprocal Rank Fusion: merge ranked index lists into one score per item."""
    fused = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)
    return fused


# --------------------------------------------------------------------------- #
# Recall                                                                       #
# --------------------------------------------------------------------------- #

def search_semantic(query: str, k: int = 5) -> str:
    """Hybrid dense+sparse recall, thresholded, diversified with MMR."""
    facts = _load()
    if not facts:
        return "Semantic memory is empty."

    # 1. dense + 2. sparse
    qv = np.asarray(_embed(query), float)
    mat = np.asarray([f["vector"] for f in facts], float)
    sims = mat @ qv / (np.linalg.norm(mat, axis=1) * np.linalg.norm(qv) + 1e-9)
    bm25 = np.asarray(_bm25_scores(query, [f["text"] for f in facts]), float)

    # 3. fuse the two rankings
    dense_rank = list(np.argsort(-sims))
    sparse_rank = list(np.argsort(-bm25))
    fused = _rrf(dense_rank, sparse_rank)

    # 4. threshold on the interpretable dense score (BM25 alone can't gate meaning)
    candidates = [i for i in range(len(facts)) if sims[i] >= MIN_SIM]
    if not candidates:
        return "No facts above the similarity threshold."

    # normalize fused scores among survivors -> 0..1 relevance for MMR
    fvals = np.array([fused[i] for i in candidates])
    span = fvals.max() - fvals.min()
    relevance = {i: (fused[i] - fvals.min()) / (span + 1e-9) for i in candidates}

    # 5. MMR: greedily pick k balancing relevance vs. redundancy to those chosen
    selected, pool = [], candidates.copy()
    while pool and len(selected) < k:
        def mmr(i):
            redundancy = max((_cos(mat[i], mat[j]) for j in selected), default=0.0)
            return MMR_LAMBDA * relevance[i] - (1 - MMR_LAMBDA) * redundancy
        best = max(pool, key=mmr)
        selected.append(best)
        pool.remove(best)

    lines = []
    for i in selected:
        srcs = ", ".join(facts[i]["sources"]) or "no source"
        lines.append(f"- {facts[i]['text']}  [{srcs}]  (sim={sims[i]:.2f})")
    return "\n".join(lines)
