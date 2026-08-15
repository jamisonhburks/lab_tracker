"""coverage — the knowledge-gap / coverage map at the method-capability grain.

Given a lab's prior-work profile (lab_profile: SCOPE = the axes it works along; COVERED = the
(modality, task) cells its publications touch), this computes `scope − covered` and classifies
each GAP cell against what methods actually exist:

  - ADOPTABLE  — a method for this (modality, task) exists in the ML methods KG (or, with deep=True,
                 the literature). The lab just hasn't used it → go adopt it.
  - OPEN FRONTIER — no established method connects the cell. A candidate methodological
                 CONTRIBUTION — the class this lab cares about.

Plus two secondary signals:
  - DEEPEN — covered (modality, task) cells missing an in-scope PARADIGM (e.g. you do
             OCT×classification but never self-supervised) — a way to extend what you have.
  - META   — how much of the lab's own modalities/tasks the ML method-KG even resolves; if little,
             the honest move is to distill literature INTO the KG (deep_fetch → record_distillation)
             rather than trust an empty cell as a true frontier.

Substrate-side and mostly offline: the KG check is a graph traversal (no model); the optional
literature check (deep=True) is best-effort and DEGRADES gracefully — an unreachable PubMed leaves
a cell labelled "literature unchecked", never silently promoted to "frontier". Disease is a filter,
not an axis (ADR-0057): these gaps are method moves meant to transfer across diseases.
"""

import re

import lab_profile
import method_select


def _ml_graph():
    return method_select._graph()          # (name, cat, adj, radj) over the fused ML seed


# Bridge the lab's CLINICAL task vocabulary to the ML KG's task naming (e.g. "disease-
# classification" → the KG's "sequence/image classification"). Modality-agnostic aliases; the
# cross-product check below lets the correct (modality, task) node pairing win.
_TASK_ALIASES = {
    "disease-classification": ["classification"],
    "multi-disease-classification": ["classification"],
    "survival": ["survival", "time-to-event"],
    "forecasting": ["forecasting"],
    "representation-learning": ["representation", "self-supervised pretraining"],
    "foundation-pretraining": ["self-supervised pretraining"],
    "segmentation": ["segmentation"],
    "generation": ["generative"],
    # Deliberately NOT aliased (kept as OPEN FRONTIER — they are this lab's contribution space,
    # not solved ML tasks): trajectory-simulation, disentanglement, downstream-transfer.
}


def _forms(axis: str, value: str, aliases: dict = None) -> list:
    """Discriminative surface forms for an axis value — its profile vocabulary + optional aliases +
    the base term before a hyphen qualifier ('OCT-longitudinal' → 'oct'). Drives KG resolution."""
    forms = list(lab_profile._VOCAB.get(axis, {}).get(value, []))
    if aliases:
        forms += aliases.get(value, [])
    forms += [value.lower().replace("-", " "), value.split("-")[0].lower()]
    return [f for f in dict.fromkeys(forms) if len(f) >= 3]


def _candidates(value: str, name: dict, cat: dict, category: str, forms: list) -> list:
    """ML-KG node ids of `category` whose name contains one of the concept forms (longest, most
    specific first). Matching on concept forms — not raw tokens — avoids qualifier collisions like
    'longitudinal OCT' vs 'longitudinal EHR'."""
    hits, cands = [], [(nid, nm.lower()) for nid, nm in name.items() if cat.get(nid) == category]
    for form in sorted(forms, key=len, reverse=True):
        for nid, nm in cands:
            if form in nm and nid not in hits:
                hits.append(nid)
    return hits


def _mods(value, name, cat):
    return _candidates(value, name, cat, "DataModality", _forms("modality", value))


def _tasks(value, name, cat):
    return _candidates(value, name, cat, "Task", _forms("task", value, _TASK_ALIASES))


def _kg_methods(modality: str, task: str, g):
    """Method names connecting (modality, task) in the ML KG: suited_to a candidate modality AND
    used_for a candidate task. None if either axis isn't in the KG at all; [] if present but no
    method connects them. Conservative — checks every candidate node pairing."""
    name, cat, adj, radj = g
    mids, tids = _mods(modality, name, cat), _tasks(task, name, cat)
    if not mids or not tids:
        return None
    methods = set()
    for mid in mids:
        suited = {s for (p, s, _) in radj.get(mid, []) if p == "suited_to"}
        for tid in tids:
            methods |= suited & {s for (p, s, _) in radj.get(tid, []) if p == "used_for"}
    return sorted(name[m] for m in methods)


def _phrase(axis_value: str) -> str:
    return axis_value.replace("-", " ").strip()


def _lit_count(modality: str, task: str):
    """Best-effort PubMed co-mention count for (modality, task) as a literature signal. None if
    the check is unreachable (offline / rate-limited)."""
    try:
        import novelty
        r = novelty.classify(_phrase(modality), _phrase(task))
        return r.get("n_pair")
    except Exception:
        return None


def _classify(modality: str, task: str, g, deep: bool):
    """→ (klass, methods, note). klass in {adoptable, frontier}."""
    methods = _kg_methods(modality, task, g)
    if methods:
        return "adoptable", methods, "ML-KG"
    if deep:
        n = _lit_count(modality, task)
        if n is None:
            return "frontier", [], "KG-empty; literature unreachable"
        if n > 0:
            return "adoptable", [], f"literature ({n} co-mentions) — distill into the KG"
        return "frontier", [], "KG-empty; no literature co-mention"
    return "frontier", [], "KG-empty; literature unchecked"


def compute(profile_id: str = None, member: str = None, deep: bool = False) -> dict:
    sc = lab_profile.scope(profile_id)
    cov = lab_profile.covered(profile_id, member)
    covered_pairs = set(tuple(p) for p in cov["pairs"])
    g = _ml_graph()

    adoptable, frontier = [], []
    for m in sc["modalities"]:
        for t in sc["tasks"]:
            if (m, t) in covered_pairs:
                continue
            klass, methods, note = _classify(m, t, g, deep)
            (adoptable if klass == "adoptable" else frontier).append((m, t, methods, note))

    # DEEPEN: covered pairs whose in-scope paradigms aren't all used.
    have = {}
    for c in cov["cells"]:
        m, t, p = c
        if p:
            have.setdefault((m, t), set()).add(p)
    deepen = []
    for (m, t) in sorted(covered_pairs):
        used = have.get((m, t), set())
        missing = [p for p in sc["paradigms"] if p not in used]
        if used and missing:                       # only when we know some paradigm and miss others
            deepen.append((m, t, missing))

    # META: how much of the lab's own axes the ML KG resolves.
    name, cat, _, _ = g
    res_m = sum(1 for m in sc["modalities"] if _mods(m, name, cat))
    res_t = sum(1 for t in sc["tasks"] if _tasks(t, name, cat))
    return {"scope": sc, "covered_pairs": sorted(covered_pairs),
            "adoptable": adoptable, "frontier": frontier, "deepen": deepen,
            "kg_resolution": (res_m, len(sc["modalities"]), res_t, len(sc["tasks"])), "deep": deep}


def render(profile_id: str = None, member: str = None, deep: bool = False) -> str:
    d = lab_profile.load(profile_id)
    if not d:
        return f"No lab profile '{profile_id or lab_profile._default_id()}' — author one first (see lab_profile)."
    r = compute(profile_id, member, deep)
    sc = r["scope"]
    total = len(sc["modalities"]) * len(sc["tasks"])
    who = f" · researcher {member}" if member else ""
    out = [f"# Coverage map — {d.get('name', d['id'])}{who}  (method-capability grain)",
           f"scope {len(sc['modalities'])} modalities × {len(sc['tasks'])} tasks = {total} cells; "
           f"covered {len(r['covered_pairs'])}; gaps {len(r['adoptable']) + len(r['frontier'])} "
           f"({len(r['frontier'])} frontier, {len(r['adoptable'])} adoptable)"]

    out.append("\n▸ OPEN FRONTIER — no established method found; candidate contributions:")
    if r["frontier"]:
        out += [f"    • {m} × {t}   [{note}]" for m, t, _, note in r["frontier"][:14]]
        if len(r["frontier"]) > 14:
            out.append(f"    … and {len(r['frontier']) - 14} more")
    else:
        out.append("    (none — every in-scope gap already has a known method)")

    out.append("\n▸ ADOPTABLE — a method exists; you just haven't used it:")
    if r["adoptable"]:
        for m, t, methods, note in r["adoptable"][:14]:
            adopt = f" → adopt: {', '.join(methods[:4])}" if methods else ""
            out.append(f"    • {m} × {t}   [{note}]{adopt}")
    else:
        out.append("    (none surfaced" + ("" if deep else " — run deep=True for a literature pass") + ")")

    if r["deepen"]:
        out.append("\n▸ DEEPEN — covered cells missing an in-scope paradigm:")
        out += [f"    • {m} × {t} — not yet: {', '.join(miss[:4])}" for m, t, miss in r["deepen"][:10]]

    rm, tm, rt, tt = r["kg_resolution"]
    out.append(f"\nMETA: the ML method-KG resolves {rm}/{tm} of your modalities and {rt}/{tt} of "
               "your tasks.")
    if rm < tm or rt < tt:
        out.append("  → Much of your scope isn't in the method-KG, so 'frontier' partly means "
                   "'not in OUR KG'. Distill literature to enrich it (deep_fetch → record_distillation), "
                   "and re-run with deep=True to separate true frontiers from unindexed methods.")
    if not deep:
        out.append("  (KG-only pass — offline. deep=True adds a best-effort PubMed check per gap.)")
    return "\n".join(out)


if __name__ == "__main__":
    # Hermetic demo: isolate a temp profile (some axes the ML seed knows, some it doesn't) and map.
    import os
    import tempfile
    from pathlib import Path

    lab_profile.PROFILES = Path(tempfile.mkdtemp())
    (lab_profile.PROFILES / "demo-lab.yaml").write_text(
        "id: demo-lab\nkind: lab\nname: Demo AI-Health Lab\n"
        "focus: multimodal foundation models; longitudinal trajectory modeling\n"
        "modalities: [ECG, genomic, OCT, OCT-longitudinal, fundus, multimodal]\n"
        "tasks: [disease-classification, survival, trajectory-simulation, disentanglement]\n"
        "paradigms: [self-supervised, foundation-model, multimodal-fusion, neural-ODE]\n",
        encoding="utf-8")
    os.environ["SUBSTRATE_LAB"] = "demo-lab"
    lab_profile.record_publication("Multimodal foundation model for OCT + fundus disease classification",
                                   year=2024, modalities="OCT,fundus,multimodal",
                                   tasks="disease-classification", paradigms="foundation-model", by="alice")

    print(render(deep=False))
