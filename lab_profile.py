"""lab_profile — a modular per-lab / per-researcher PRIOR-WORK profile.

Coverage of "what we don't know" is only meaningful relative to what a specific lab has already
done. This is that baseline: a lab (or researcher) declares its SCOPE — the axes it works along —
and records its PUBLICATIONS, tagged onto the same axes. The unit is modular: each lab ships its
own `profiles/<id>.yaml`; per-researcher views filter by author.

The atoms are the method-capability grain this lab actually thinks in (not gene↔disease links):
  - MODALITY  (incl. combinations): OCT, longitudinal-OCT, fundus, EHR-physiological, ECG, …
  - TASK / question-type: multi-disease classification, trajectory simulation, disentanglement,
    foundation-pretraining, downstream transfer, …
  - PARADIGM / learning approach: self-supervised, foundation-model, multimodal-fusion,
    neural-ODE, state-space, causal-representation, …

Two products, split along the substrate/thinker line (ADR-0030):
  - `scope()` + `covered()` — STRUCTURED sets the coverage map (coverage.py) subtracts to find
    gaps. LLM-free.
  - `profile_context()` — the profile + tagged publications as IN-CONTEXT grounding, so the
    thinker (Claude) can phrase gaps in the lab's language and propose the next method. The
    "in-context learning" happens thinker-side; the substrate only stores and serves.

A publication/work corpus personalizes to the WORK, not the person — in bounds per ADR-0052.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import store_lock

ROOT = Path(__file__).parent
PROFILES = ROOT / "profiles"

# Canonical axis vocabulary for AI-for-health, each with surface forms for heuristic tagging.
# Extensible: a profile/publication may use values outside this seed; the vocab only drives
# normalization + the keyword auto-tagger, it is not a closed set.
_VOCAB = {
    "modality": {
        "OCT": ["oct", "optical coherence tomography"],
        "OCT-longitudinal": ["longitudinal oct", "oct trajectory", "oct over time", "serial oct"],
        "fundus": ["fundus", "color fundus", "retinal photograph", "retinal fundus"],
        "EHR-physiological": ["physiological", "physiologic", "vital sign", "waveform ehr"],
        "EHR-labs": ["lab value", "laboratory", "labs"],
        "EHR": ["ehr", "electronic health record", "clinical record"],
        "ECG": ["ecg", "ekg", "electrocardiogram"],
        "waveform": ["waveform", "ppg", "signal"],
        "genomic": ["genomic", "genome", "gwas", "polygenic", "prs"],
        "imaging": ["imaging", "mri", "ct scan", "radiolog"],
        "text": ["clinical note", "free text", "nlp", "report text"],
        "multimodal": ["multimodal", "multi-modal", "multiple modalities", "cross-modal"],
    },
    "task": {
        "multi-disease-classification": ["multi-disease", "multidisease", "multi disease",
                                         "multilabel disease", "comorbid"],
        "disease-classification": ["disease classification", "diagnosis", "classify disease",
                                   "disease prediction", "disease detection"],
        "trajectory-simulation": ["trajectory", "simulate", "latent trajectory",
                                  "disease progression", "progression model"],
        "forecasting": ["forecast", "predict future", "time-series prediction"],
        "representation-learning": ["representation learning", "embedding", "latent representation"],
        "disentanglement": ["disentangl", "separate representation", "invariance",
                            "invariant representation", "factor"],
        "foundation-pretraining": ["pretrain", "pre-train", "foundation model",
                                   "self-supervised pretraining"],
        "downstream-transfer": ["downstream", "transfer", "fine-tune", "finetune", "linear probe"],
        "survival": ["survival", "time-to-event", "time to event"],
        "segmentation": ["segmentation", "segment"],
    },
    "paradigm": {
        "self-supervised": ["self-supervised", "self supervised", "ssl", "contrastive", "masked"],
        "foundation-model": ["foundation model", "foundation-model", "pretrained backbone"],
        "multimodal-fusion": ["fusion", "cross-attention", "cross attention", "multimodal fusion"],
        "neural-ODE": ["neural ode", "latent sde", "continuous-time", "ode-", "neural-ode"],
        "state-space": ["state space", "state-space", "ssm", "mamba", "s4"],
        "diffusion": ["diffusion"],
        "transformer": ["transformer", "vit", "attention-based"],
        "GNN": ["graph neural", "gnn", "graph network"],
        "causal-representation": ["causal representation", "causal", "counterfactual",
                                  "invariant risk"],
        "domain-adaptation": ["domain adaptation", "domain shift", "distribution shift"],
    },
}
AXES = list(_VOCAB.keys())


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _contributor() -> str:
    return os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "unknown"


# --------------------------------------------------------------------------- #
# Profile + publications I/O.                                                  #
# --------------------------------------------------------------------------- #
def list_profiles() -> list:
    return sorted(p.stem for p in PROFILES.glob("*.yaml")) if PROFILES.exists() else []


def _default_id() -> str:
    env = os.environ.get("SUBSTRATE_LAB")
    if env:
        return env
    ids = list_profiles()
    return ids[0] if len(ids) == 1 else (ids[0] if ids else "helmholtz-ai-health")


def load(profile_id: str = None) -> dict:
    pid = profile_id or _default_id()
    f = PROFILES / f"{pid}.yaml"
    if not f.exists():
        return {}
    try:
        import yaml
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        d.setdefault("id", pid)
        return d
    except Exception:
        return {}


def _pub_path(pid: str) -> Path:
    return PROFILES / f"{pid}.publications.jsonl"


def publications(profile_id: str = None, member: str = None) -> list:
    pid = profile_id or _default_id()
    p = _pub_path(pid)
    if not p.exists():
        return []
    out = [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]
    return [r for r in out if not member or r.get("by") == member]


# --------------------------------------------------------------------------- #
# Tagging onto the axes.                                                       #
# --------------------------------------------------------------------------- #
def _normalize(axis: str, value: str) -> str:
    """Map a surface form to its canonical axis value; pass through if unknown (open vocab).
    Exact canonical match wins first, so a specific value ('OCT-longitudinal') isn't swallowed by
    a shorter one ('OCT'); surface-form matches then prefer the longest (most specific) canon."""
    v = value.strip()
    low = v.lower()
    table = _VOCAB.get(axis, {})
    for canon in table:                              # exact canonical match first
        if low == canon.lower():
            return canon
    for canon in sorted(table, key=len, reverse=True):   # then longest surface-form match
        if any(f in low for f in table[canon]):
            return canon
    return v


def _split(csv: str) -> list:
    return [t.strip() for t in csv.split(",") if t.strip()] if csv else []


def auto_tag(text: str) -> dict:
    """Heuristic keyword tagging of free text onto the axes (a convenience, not an LLM — richer
    tagging is a thinker step). Returns {modality:[…], task:[…], paradigm:[…]}."""
    low = (text or "").lower()
    tags = {}
    for axis, table in _VOCAB.items():
        hit = [canon for canon, forms in table.items()
               if canon.lower() in low or any(f in low for f in forms)]
        tags[axis] = sorted(set(hit))
    return tags


def record_publication(title: str, year=None, modalities: str = "", tasks: str = "",
                       paradigms: str = "", ref: str = "", by=None, profile_id: str = None) -> str:
    """Add a publication to a lab's profile — the COVERED work. Explicit `modalities`/`tasks`/
    `paradigms` (comma-separated) are normalized to canonical axis values; any axis left blank is
    auto-tagged from the title (heuristic). Attributed + append-only."""
    pid = profile_id or _default_id()
    auto = auto_tag(title)
    tagged = {}
    for axis, given in (("modality", modalities), ("task", tasks), ("paradigm", paradigms)):
        vals = [_normalize(axis, v) for v in _split(given)] or auto.get(axis, [])
        tagged[axis] = sorted(set(vals))
    rec = {"ts": _now(), "by": by or _contributor(), "title": title.strip(),
           "year": year, "ref": ref.strip() or None,
           "modalities": tagged["modality"], "tasks": tagged["task"],
           "paradigms": tagged["paradigm"]}
    PROFILES.mkdir(parents=True, exist_ok=True)
    store_lock.append_jsonl(_pub_path(pid), rec)
    cells = len(rec["modalities"]) * max(1, len(rec["tasks"]))
    return (f"publication added to {pid}: {title[:60]} "
            f"[{'/'.join(rec['modalities']) or '?'} × {'/'.join(rec['tasks']) or '?'}"
            f"{' · ' + '/'.join(rec['paradigms']) if rec['paradigms'] else ''}] → {cells} cell(s)")


# --------------------------------------------------------------------------- #
# The two products: scope (relevant region) and covered (what pubs cover).      #
# --------------------------------------------------------------------------- #
def _dedup(seq: list) -> list:
    return list(dict.fromkeys(seq))


def scope(profile_id: str = None) -> dict:
    """The lab's declared axes — the RELEVANT region the coverage map is computed over."""
    d = load(profile_id)
    return {"modalities": _dedup(_normalize("modality", m) for m in d.get("modalities", [])),
            "tasks": _dedup(_normalize("task", t) for t in d.get("tasks", [])),
            "paradigms": _dedup(_normalize("paradigm", p) for p in d.get("paradigms", []))}


def covered(profile_id: str = None, member: str = None) -> dict:
    """What the lab has COVERED, from its publications: the axis values touched, the (modality,
    task) pairs, and (modality, task, paradigm) cells. The set the coverage map subtracts."""
    mods, tasks, paras, pairs, cells = set(), set(), set(), set(), set()
    for pub in publications(profile_id, member):
        pm, pt, pp = (pub.get("modalities") or [], pub.get("tasks") or [],
                      pub.get("paradigms") or [None])
        mods.update(pm); tasks.update(pt); paras.update(x for x in pp if x)
        for m in pm:
            for t in pt:
                pairs.add((m, t))
                for p in pp:
                    cells.add((m, t, p))
    return {"modalities": sorted(mods), "tasks": sorted(tasks), "paradigms": sorted(paras),
            "pairs": sorted(pairs), "cells": sorted(c for c in cells)}


# --------------------------------------------------------------------------- #
# Rendering: structured summary + thinker in-context grounding.                #
# --------------------------------------------------------------------------- #
def render(profile_id: str = None, member: str = None) -> str:
    d = load(profile_id)
    if not d:
        return (f"No profile '{profile_id or _default_id()}'. Author profiles/<id>.yaml "
                "(id, kind, focus, modalities, tasks, paradigms) — see the seeded example.")
    cov, sc = covered(profile_id, member), scope(profile_id)
    who = f" · researcher {member}" if member else ""
    pubs = publications(profile_id, member)
    out = [f"Lab profile — {d.get('name', d['id'])}{who}",
           f"  focus: {str(d.get('focus', '')).strip()[:200]}",
           f"  scope: {len(sc['modalities'])} modalities × {len(sc['tasks'])} tasks × "
           f"{len(sc['paradigms'])} paradigms",
           f"  covered: {len(pubs)} publication(s) → {len(cov['pairs'])} modality×task pair(s), "
           f"{len(cov['cells'])} full cell(s)"]
    if cov["pairs"]:
        out.append("  covered pairs: " + ", ".join(f"{m}×{t}" for m, t in cov["pairs"][:12]))
    return "\n".join(out)


def profile_context(profile_id: str = None, member: str = None) -> str:
    """The profile + tagged publications, rendered for the THINKER to reason over IN CONTEXT —
    to phrase coverage gaps in the lab's language and propose the next method. Substrate serves;
    thinker thinks."""
    d = load(profile_id)
    if not d:
        return f"No profile '{profile_id or _default_id()}'."
    sc = scope(profile_id)
    out = [f"# Prior-work profile — {d.get('name', d['id'])}"
           + (f" (researcher: {member})" if member else ""),
           f"\nFocus: {str(d.get('focus', '')).strip()}",
           "\nScope (axes the lab works along):",
           f"  modalities: {', '.join(sc['modalities']) or '—'}",
           f"  tasks:      {', '.join(sc['tasks']) or '—'}",
           f"  paradigms:  {', '.join(sc['paradigms']) or '—'}",
           "\nPublications (what the lab has already covered):"]
    pubs = publications(profile_id, member)
    if not pubs:
        out.append("  (none recorded yet — record_publication to seed the covered region)")
    for p in pubs[:40]:
        tag = " · ".join(filter(None, ["/".join(p.get("modalities") or []),
                                       "/".join(p.get("tasks") or []),
                                       "/".join(p.get("paradigms") or [])]))
        yr = f" ({p['year']})" if p.get("year") else ""
        out.append(f"  - {p.get('title', '?')}{yr}  [{tag}]  ← {p.get('by', '?')}")
    out.append("\nUse this to ground gap-finding: propose method moves in cells the SCOPE covers "
               "but the PUBLICATIONS do not — favouring transfer across diseases.")
    return "\n".join(out)


if __name__ == "__main__":
    # Hermetic demo: isolate a temp profiles dir, seed a profile, record pubs, show the products.
    import tempfile

    PROFILES = Path(tempfile.mkdtemp())
    (PROFILES / "demo-lab.yaml").write_text(
        "id: demo-lab\nkind: lab\nname: Demo AI-Health Lab\nmembers: [alice]\n"
        "focus: multimodal foundation models and longitudinal trajectory modeling\n"
        "modalities: [OCT, OCT-longitudinal, fundus, EHR-physiological, genomic, multimodal]\n"
        "tasks: [multi-disease-classification, trajectory-simulation, disentanglement, "
        "foundation-pretraining]\n"
        "paradigms: [self-supervised, foundation-model, multimodal-fusion, neural-ODE]\n",
        encoding="utf-8")
    os.environ["SUBSTRATE_LAB"] = "demo-lab"

    print(record_publication("Multimodal foundation model for OCT and fundus disease classification",
                             year=2024, by="alice"))
    print(record_publication("Contrastive self-supervised pretraining of ECG representations",
                             year=2023, modalities="ECG", by="bob"))
    print()
    print(render())
    print("\n--- scope vs covered (what coverage.py will diff) ---")
    print("scope tasks   :", scope()["tasks"])
    print("covered pairs :", covered()["pairs"])
    print("\n--- thinker in-context grounding ---")
    print(profile_context())
