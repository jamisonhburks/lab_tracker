"""method_select — KG-grounded ML method selection over the fused ml_schema graph.

Turns "what method for this data?" from a hardcoded lookup into a GRAPH TRAVERSAL:
  DataModality  —suited_to←  Architecture  —used_for→ Task  —evaluated_by→ Metric
                                            —trained_with→ Loss
plus the modality's has_caveat and encoding standards, and each architecture's real
authorship/year. Respects the epistemic trust split (stable methodological edges vs
benchmark-relative, low-trust).

Backend-independent: it reads the fused ML seed directly (ml_schema.load_fused_seed), so
it works whatever the main KG_BACKEND is. If a disease isn't bridged to a modality yet
(the bridge is curated — Stage 2 expands it), it says so rather than guessing.
"""

import re

import ml_schema

_LOW = ("benchmark", "leaderboard", "sota")


def _graph():
    nodes, edges = ml_schema.load_fused_seed()
    name = {n[0]: n[1] for n in nodes}
    cat = {n[0]: n[2] for n in nodes}
    adj, radj = {}, {}
    for s, p, o, src in edges:
        adj.setdefault(s, []).append((p, o, src))
        radj.setdefault(o, []).append((p, s, src))
    return name, cat, adj, radj


def _resolve(term: str, name: dict, cat: dict) -> str | None:
    low = term.strip().lower()
    for pref in ("DataModality", "Disease", "Task"):          # exact name, by category
        for nid, nm in name.items():
            if cat.get(nid) == pref and nm.lower() == low:
                return nid
    for pref in ("DataModality", "Disease"):                  # substring, prefer modality
        for nid, nm in name.items():
            if cat.get(nid) == pref and low in nm.lower():
                return nid
    return next((nid for nid, nm in name.items() if low in nm.lower()), None)


def _year(pub_label: str) -> str:
    m = re.search(r"\((\d{4})\)", pub_label or "")
    return m.group(1) if m else ""


def recommend_methods(target: str) -> str:
    """Recommend ML methods for a data modality — or for a disease (via its modalities)."""
    name, cat, adj, radj = _graph()
    tid = _resolve(target, name, cat)
    if tid is None:
        return f"'{target}' not found in the ML method graph."

    if cat.get(tid) == "DataModality":
        mods = [tid]
    else:                                                     # disease -> its modalities
        mods = [o for (p, o, _) in adj.get(tid, []) if p in ("manifests_in", "studied_via")]
        if not mods:
            return (f"No data modality is linked to {name.get(tid, target)} in the graph "
                    "(the biomedical↔ML bridge is curated — Stage 2 expands coverage).")

    out = [f"KG-grounded method selection for: {name.get(tid, target)}"]
    for mid in mods:
        out.append(f"\n▸ modality: {name[mid]}")
        cav = [name[o] for (p, o, _) in adj.get(mid, []) if p == "has_caveat"]
        std = [name[s] for (p, s, _) in radj.get(mid, []) if p == "encodes"]
        if std:
            out.append(f"    encoded by: {', '.join(std)}")
        if cav:
            out.append(f"    caveat: {', '.join(cav)}")
        archs = [(s, src) for (p, s, src) in radj.get(mid, []) if p == "suited_to"]
        if not archs:
            out.append("    (no suited method in graph)")
            continue
        out.append("    suited methods (graph-grounded):")
        for aid, src in archs:
            auth = next((name[o] for (p, o, _) in adj.get(aid, []) if p == "first_author"), "")
            pub = next((name[o] for (p, o, _) in adj.get(aid, []) if p == "introduced_by"), "")
            losses = [name[o] for (p, o, _) in adj.get(aid, []) if p == "trained_with"]
            tasks = [o for (p, o, _) in adj.get(aid, []) if p == "used_for"]
            metrics = []
            for t in tasks:
                metrics += [name[o] for (p, o, _) in adj.get(t, []) if p == "evaluated_by"]
            trust = "benchmark/low-trust" if any(k in src.lower() for k in _LOW) else "methodological"
            desc = f"      - {name[aid]}" + (f" ({auth} {_year(pub)})".rstrip() if auth else "")
            extra = []
            if losses:
                extra.append("loss: " + ", ".join(dict.fromkeys(losses)))
            if metrics:
                extra.append("metric: " + ", ".join(dict.fromkeys(metrics)))
            extra.append(f"[{trust}]")
            out.append(desc + "  " + " | ".join(extra))
    out.append("\n(selection = traversal modality→suited_to→used_for→trained_with→"
               "evaluated_by; stable edges vs benchmark flagged.)")
    return "\n".join(out)
