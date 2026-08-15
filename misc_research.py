"""misc_research — the exploratory / un-hypothesized lane.

Not every session tests a pre-registered hypothesis; a lot of real work is just running
analyses. Forcing that into the formal Research Workflow loses it. This module handles the
exploratory mode honestly, without lowering the rigor bar:

  LOG    a miscellaneous finding into the lab's exploratory pool — NOT tied to a hypothesis,
         but still RIGOR-evaluated (a claim + a method + some evidence). Underspecified ones
         are logged but flagged, not silently accepted.
  MATCH  each misc finding against the coherent lab KG + curated consensus + active
         hypotheses: does it corroborate / contradict / relate to known work, or is it an
         orphan (grounded-novel or off-graph)?
  GROUP  orphan misc findings by shared entities: clusters that TOGETHER imply a latent
         hypothesis worth formalizing — turning scattered analyses into a coherent question.

Store: memory/misc_findings.jsonl (append-only, attributed, with rigor verdict + match).
The rigor gate is thinker-suppliable (a Claude client passes its own verdict — ADR-0040) with
a heuristic fallback; MATCH/GROUP are pure substrate (no LLM).
"""
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import kg_memory as kg
import kg_writer
import store_lock

ROOT = Path(__file__).parent
MISC_LOG = ROOT / "memory" / "misc_findings.jsonl"


def _contributor() -> str:
    return os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "unknown"


def _load() -> list:
    if not MISC_LOG.exists():
        return [json.loads(l) for l in [] ]
    return [json.loads(l) for l in MISC_LOG.open(encoding="utf-8") if l.strip()]


# --------------------------------------------------------------------------- #
# Rigor gate (thinker-suppliable, heuristic fallback).                         #
# --------------------------------------------------------------------------- #
def _rigor(claim: str, method: str, has_evidence: bool, supplied=None) -> dict:
    """Evaluate a misc finding for rigor. Verdicts: accept | flag | reject.
    A miss on a claim is a reject; a miss on method/evidence is a FLAG (logged but marked
    'needs rigor') so the analysis isn't lost — it can be firmed up. `supplied` (a thinker's
    verdict) overrides the heuristic."""
    if supplied is not None:
        v = supplied if isinstance(supplied, dict) else {"verdict": supplied}
        verdict = str(v.get("verdict", "")).strip().lower()
        verdict = verdict if verdict in ("accept", "flag", "reject") else "flag"
        return {"verdict": verdict, "reason": v.get("reason", "thinker rigor verdict"),
                "by": "thinker"}
    if not claim.strip():
        return {"verdict": "reject", "reason": "no claim stated", "by": "heuristic"}
    if not method.strip():
        return {"verdict": "flag", "reason": "underspecified: no method given", "by": "heuristic"}
    if not has_evidence:
        return {"verdict": "flag",
                "reason": "underspecified: no quantitative evidence (effect / p / n / source)",
                "by": "heuristic"}
    return {"verdict": "accept", "reason": "claim + method + evidence present", "by": "heuristic"}


# --------------------------------------------------------------------------- #
# Match a misc finding against the coherent lab KG / consensus / active work.   #
# --------------------------------------------------------------------------- #
def _active_hypotheses(*entities) -> list:
    """Hypothesis ids whose spec mentions any of the entities (relates-to-active-work)."""
    hits = []
    ents = [e.strip().lower() for e in entities if e and e.strip()]
    for f in sorted((ROOT / "hypotheses").glob("*.y*ml")) if (ROOT / "hypotheses").exists() else []:
        text = f.read_text(encoding="utf-8").lower()
        if any(e in text for e in ents):
            hits.append(f.stem.split("_")[0])
    return sorted(set(hits))


def match_misc(subject: str, object: str, claim: str = "") -> dict:
    """Match a misc finding against the lab's coherent knowledge — no LLM."""
    if not (subject and object):
        return {"verdict": "unmatchable", "note": "need a subject and object to match"}
    grounding = kg.check_connection(subject, object)
    curated = [r for r in kg_writer.query(subject, object)]
    active = _active_hypotheses(subject, object)
    if curated:
        verdict = "corroborates_consensus"
    elif active:
        verdict = f"relates_to_active_work ({', '.join(active)})"
    elif grounding in ("grounded", "weakly_grounded"):
        verdict = "grounded_but_uncurated (candidate to formalize)"
    else:
        verdict = "orphan (novel / off-graph — group with peers or verify)"
    return {"verdict": verdict, "grounding": grounding,
            "curated_matches": len(curated), "active_hypotheses": active}


# --------------------------------------------------------------------------- #
# Log a misc finding.                                                          #
# --------------------------------------------------------------------------- #
def log_misc(claim: str, subject: str = "", object: str = "", method: str = "",
             data: str = "", effect_size=None, p_value=None, sample_size=None,
             source: str = "", rigor_verdict=None, contributor=None) -> str:
    """Log one miscellaneous (un-hypothesized) finding — rigor-gated, then matched against the
    lab KG. Not consensus: it lives in the exploratory pool until it matches or is grouped +
    formalized. `contributor` is the per-request caller identity (shared HTTP deployment)."""
    s_norm = kg.normalize_entity(subject) if subject else None
    o_norm = kg.normalize_entity(object) if object else None
    subj = s_norm["name"] if s_norm else subject.strip()
    obj = o_norm["name"] if o_norm else object.strip()
    has_ev = any(x is not None for x in (effect_size, p_value, sample_size)) or bool(source.strip())

    rigor = _rigor(claim, method, has_ev, supplied=rigor_verdict)
    match = match_misc(subj, obj, claim) if (subj and obj) else {"verdict": "unmatchable"}

    entry = {"ts": datetime.now().isoformat(timespec="seconds"),
             "contributor": contributor or _contributor(),
             "claim": claim.strip(), "subject": subj, "object": obj, "method": method.strip(),
             "data": data.strip(), "effect_size": effect_size, "p_value": p_value,
             "sample_size": sample_size, "source": source.strip(),
             "rigor": rigor["verdict"], "rigor_reason": rigor["reason"], "rigor_by": rigor["by"],
             "match": match["verdict"]}
    if rigor["verdict"] == "reject":
        return f"misc finding REJECTED (not logged): {rigor['reason']}"
    store_lock.append_jsonl(MISC_LOG, entry)               # locked append (shared-safe)
    out = [f"logged misc finding [{rigor['verdict']} by {rigor['by']}]: {claim[:80]}"]
    if rigor["verdict"] == "flag":
        out.append(f"  ⚠ rigor: {rigor['reason']}")
    out.append(f"  match vs lab knowledge: {match['verdict']}")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Group orphan misc findings into latent themes (shared-entity clustering).     #
# --------------------------------------------------------------------------- #
def _canon_key(entity: str) -> str:
    """A canonical grouping key for an entity: the KG node id if it resolves (so SYNONYMS that
    map to the same node — 'AF'/'atrial fibrillation', gene aliases, disease synonyms via
    ENTITY_NORM=semantic — collapse to one key), else the lowercased string."""
    e = (entity or "").strip()
    if not e:
        return ""
    for fn in ((lambda x: (kg.normalize_entity(x) or {}).get("id")),
               (lambda x: kg._resolve(x))):
        try:
            k = fn(e)
            if k:
                return k
        except Exception:
            pass
    return e.lower()


def _key_label(k: str) -> str:
    try:
        from kg_memory import _label
        lbl = _label(k)
        return lbl if lbl and lbl != k else k
    except Exception:
        return k


# Two-layer semantics: KG normalization (_canon_key) is the ONTOLOGY-synonym layer (gene
# aliases via gene_norm, disease synonyms via ENTITY_NORM=semantic / _resolve) — it collapses
# 'IL8'→CXCL8, 'heart attack'→the MI node, etc. The embedding merge below is a PRECISION-FIRST
# bonus for OFF-graph surface variants the KG can't resolve ('type 2 diabetes' vs '... mellitus').
# nomic-embed-text scores near-duplicates ~0.95 but weak on true synonyms, so the threshold is
# high on purpose — real synonyms are the KG layer's job, not this one.
_SEM_THRESHOLD = 0.80


def _semantic_merge(keys: set) -> dict:
    """Merge near-duplicate ORPHAN string keys (not resolved to a KG node) by embedding cosine.
    Returns {key -> representative}. Graceful: if the embedder (ollama) is unavailable, identity."""
    rep = {k: k for k in keys}
    raw = [k for k in keys if ":" not in k]            # KG ids carry a prefix ':'; orphans don't
    if len(raw) < 2:
        return rep
    try:
        import numpy as np
        import semantic_memory as sm
        vecs = {k: np.array(sm._embed(k), dtype=float) for k in raw}
    except Exception:
        return rep

    def cos(a, b):
        d = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(a @ b / d)

    parent = {k: k for k in raw}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x

    for i, a in enumerate(raw):
        for b in raw[i + 1:]:
            if cos(vecs[a], vecs[b]) >= _SEM_THRESHOLD:
                parent[find(a)] = find(b)
    for k in raw:
        rep[k] = find(k)
    return rep


def _clusters(min_group: int = 2, semantic: bool = True) -> list:
    """Connected components of misc findings linked by a shared CANONICAL entity (KG-normalized,
    optionally semantically merged). Returns [{indices, shared, findings}]."""
    findings = _load()
    keys_per, all_keys = [], set()
    for f in findings:
        ks = {k for k in (_canon_key(f.get("subject")), _canon_key(f.get("object"))) if k}
        keys_per.append(ks); all_keys |= ks
    rep = _semantic_merge(all_keys) if semantic else {k: k for k in all_keys}
    keys_per = [{rep.get(k, k) for k in ks} for ks in keys_per]

    ent2idx = defaultdict(set)
    for i, ks in enumerate(keys_per):
        for k in ks:
            ent2idx[k].add(i)
    adj = defaultdict(set)
    for idxs in ent2idx.values():
        idxs = list(idxs)
        for a in idxs:
            adj[a].update(x for x in idxs if x != a)

    seen, comps = set(), []
    for i in range(len(findings)):
        if i in seen:
            continue
        comp, stack = [], [i]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.append(x); stack.extend(adj[x] - seen)
        if len(comp) >= min_group:
            shared = sorted(_key_label(k) for k, idxs in ent2idx.items()
                            if len(idxs & set(comp)) >= 2)
            comps.append({"indices": sorted(comp), "shared": shared,
                          "findings": [findings[j] for j in sorted(comp)]})
    return comps


def group_misc(min_group: int = 2, semantic: bool = True) -> str:
    """Cluster misc findings by shared entity — KG-normalized so SYNONYMS collapse, plus an
    optional embedding merge for off-graph synonyms. A cluster of >=2 is a latent theme;
    formalize it in one step with formalize_group(N)."""
    findings = _load()
    if not findings:
        return "No misc findings logged yet."
    comps = _clusters(min_group, semantic)
    if not comps:
        return (f"{len(findings)} misc finding(s), no cluster of >={min_group} sharing an "
                "entity yet. Keep logging; themes emerge as they accrue.")
    out = [f"{len(comps)} latent theme(s) across {len(findings)} misc finding(s) "
           "(entities merged semantically where possible):"]
    for gi, c in enumerate(comps, 1):
        out.append(f"\n  Theme {gi} — shared: {', '.join(c['shared']) or '(chained entities)'}"
                   f"   → formalize_group({gi})")
        for f in c["findings"]:
            out.append(f"    · {f['claim'][:80]}  [{f.get('match', '?')}]")
    return "\n".join(out)


def hypothesis_stub(entities, methods, observations, header: str = "") -> str:
    """Shared drafter: assemble a hypothesis + method YAML stub from entities/methods/
    observations. Used by both a session (formalize_retroactively) and a misc cluster
    (formalize_group), so a retroactive hypothesis looks the same however it was triggered."""
    ents = [e for e in dict.fromkeys(entities) if e][:4]
    lines = [header or "# DRAFT hypothesis — REVIEW + COMPLETE before use.",
             "id: H000   # assign the next H00N",
             f'title: "(draft) {" / ".join(ents[:2]) or "exploratory cluster"}"',
             'question: "(what do these analyses jointly ask?)"',
             'null_hypothesis: "H0: ..."',
             'alternative_hypothesis: "H1: ..."',
             f"entities: [{', '.join(ents)}]",
             "method: |"]
    lines += [f"  - {str(m)[:100]}" for m in methods[:6]] or ["  (fill from the analyses)"]
    lines += ["observed: |"]
    lines += [f"  - {str(o)[:100]}" for o in observations[:6]] or ["  (none captured)"]
    lines += ['status: "draft"']
    return "\n".join(lines)


def formalize_group(theme: int = 1) -> str:
    """Turn a GROUP of misc findings (from group_misc, theme N) straight into a DRAFT hypothesis
    + method stub — one step from scattered analyses to a formalizable hypothesis. Review/
    complete, then save to hypotheses/H00N_*.yaml (shared WIP)."""
    comps = _clusters()
    if not comps:
        return "No cluster of misc findings to formalize yet (need >=2 sharing an entity)."
    if theme < 1 or theme > len(comps):
        return f"Theme {theme} out of range (1..{len(comps)})."
    fs = comps[theme - 1]["findings"]
    entities, methods, obs = [], [], []
    for f in fs:
        for e in (f.get("subject"), f.get("object")):
            if e:
                entities.append(e)
        if f.get("method"):
            methods.append(f["method"])
        obs.append(f"{f['claim']} (effect={f.get('effect_size')}, p={f.get('p_value')}, "
                   f"match={f.get('match', '?')})")
    return hypothesis_stub(entities, methods, obs,
                           header=f"# RETROACTIVELY DRAFTED from misc cluster (theme {theme}) — "
                                  "REVIEW + COMPLETE before use.")


def list_misc(limit: int = 20) -> str:
    findings = _load()
    if not findings:
        return "No misc findings logged yet."
    lines = [f"Miscellaneous findings ({len(findings)}):"]
    for f in findings[-limit:]:
        lines.append(f"  [{f['contributor']}] {f['claim'][:70]}  "
                     f"(rigor={f['rigor']}, match={f.get('match', '?')})")
    return "\n".join(lines)
