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
             source: str = "", rigor_verdict=None) -> str:
    """Log one miscellaneous (un-hypothesized) finding — rigor-gated, then matched against the
    lab KG. Not consensus: it lives in the exploratory pool until it matches or is grouped +
    formalized."""
    s_norm = kg.normalize_entity(subject) if subject else None
    o_norm = kg.normalize_entity(object) if object else None
    subj = s_norm["name"] if s_norm else subject.strip()
    obj = o_norm["name"] if o_norm else object.strip()
    has_ev = any(x is not None for x in (effect_size, p_value, sample_size)) or bool(source.strip())

    rigor = _rigor(claim, method, has_ev, supplied=rigor_verdict)
    match = match_misc(subj, obj, claim) if (subj and obj) else {"verdict": "unmatchable"}

    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "contributor": _contributor(),
             "claim": claim.strip(), "subject": subj, "object": obj, "method": method.strip(),
             "data": data.strip(), "effect_size": effect_size, "p_value": p_value,
             "sample_size": sample_size, "source": source.strip(),
             "rigor": rigor["verdict"], "rigor_reason": rigor["reason"], "rigor_by": rigor["by"],
             "match": match["verdict"]}
    if rigor["verdict"] == "reject":
        return f"misc finding REJECTED (not logged): {rigor['reason']}"
    MISC_LOG.parent.mkdir(parents=True, exist_ok=True)
    with MISC_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    out = [f"logged misc finding [{rigor['verdict']} by {rigor['by']}]: {claim[:80]}"]
    if rigor["verdict"] == "flag":
        out.append(f"  ⚠ rigor: {rigor['reason']}")
    out.append(f"  match vs lab knowledge: {match['verdict']}")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Group orphan misc findings into latent themes (shared-entity clustering).     #
# --------------------------------------------------------------------------- #
def group_misc(min_group: int = 2) -> str:
    """Cluster misc findings by shared entities (connected components). A cluster of >=2
    findings that share an entity is a latent theme — several scattered analyses that,
    together, may imply a hypothesis worth formalizing. No LLM: pure entity overlap."""
    findings = _load()
    if not findings:
        return "No misc findings logged yet."
    ent2idx = defaultdict(set)
    for i, f in enumerate(findings):
        for e in (f.get("subject"), f.get("object")):
            e = (e or "").strip().lower()
            if e:
                ent2idx[e].add(i)
    adj = defaultdict(set)                       # findings sharing any entity are linked
    for idxs in ent2idx.values():
        idxs = list(idxs)
        for a in idxs:
            adj[a].update(x for x in idxs if x != a)
    seen, groups = set(), []
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
            groups.append(sorted(comp))
    if not groups:
        return (f"{len(findings)} misc finding(s), no cluster of >={min_group} sharing an "
                "entity yet. Keep logging; themes emerge as they accrue.")
    out = [f"{len(groups)} latent theme(s) across {len(findings)} misc finding(s) "
           "(findings sharing an entity — each may imply a hypothesis to formalize):"]
    for gi, comp in enumerate(groups, 1):
        shared = sorted(e for e, idxs in ent2idx.items() if len(idxs & set(comp)) >= 2)
        out.append(f"\n  Theme {gi} — shared: {', '.join(shared) or '(chained entities)'}")
        for i in comp:
            f = findings[i]
            out.append(f"    · {f['claim'][:80]}  [{f.get('match', '?')}]")
        out.append("    → consider formalizing this cluster as one hypothesis (→ shared WIP).")
    return "\n".join(out)


def list_misc(limit: int = 20) -> str:
    findings = _load()
    if not findings:
        return "No misc findings logged yet."
    lines = [f"Miscellaneous findings ({len(findings)}):"]
    for f in findings[-limit:]:
        lines.append(f"  [{f['contributor']}] {f['claim'][:70]}  "
                     f"(rigor={f['rigor']}, match={f.get('match', '?')})")
    return "\n".join(lines)
