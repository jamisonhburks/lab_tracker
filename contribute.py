"""contribute — the write-path from a validated finding into SHARED CONSENSUS knowledge.

The one tier behind a gate. A finding is normalized to canonical entities, critic-gated
(the CI check), routed conservatively, and appended to the shared contributions log with
ATTRIBUTION + provenance + verdict:

  - reject          : critic caught junk / unsupported → not recorded as knowledge.
  - auto_merged     : corroborates an already-`supported` edge (same direction) AND critic
                      accepts → merged into the consensus curated KG; evidence + confidence
                      update (multi-user evidence aggregation).
  - pending_review  : NOVEL edge, or one that would CONTRADICT / shift a status → held for
                      peer review (lives in shared WIP, not yet consensus).

Aggregation is the confidence projection over accumulated evidence (kg_writer + confidence)
— more independent contributors on an edge → sharper, power-weighted confidence.

Contribution TYPES: `literature` (critic re-reads the cited abstract) and `experiment`
(a completed experiment's finding — verified by its committed provenance, not an abstract).

In the git deployment this append == a PR, the critic == CI, review == PR approval, merge
== accept. Locally it appends to memory/lab_contributions.jsonl and, on auto-merge, writes
the consensus curated KG. Contributor id from SUBSTRATE_CONTRIBUTOR / $USER.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import kg_memory as kg
import kg_writer
import confidence
import critic

ROOT = Path(__file__).parent
CONTRIB_LOG = ROOT / "memory" / "lab_contributions.jsonl"


def _contributor() -> str:
    return os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "unknown"


def _critic_gate(subj: str, predicate: str, obj: str, source: str,
                 source_kind: str, abstract) -> dict:
    """Experiment findings are verified by committed provenance; literature by the critic
    re-reading the cited abstract."""
    if source_kind == "experiment":
        exp = source.split(":")[-1].strip()
        if critic._looks_like_junk(subj) or critic._looks_like_junk(obj):
            return {"verdict": "reject", "reason": "entity is a junk id/accession"}
        prov = (ROOT / "experiments" / exp).exists() or \
               (ROOT / "reports" / f"{exp}_evaluation.md").exists()
        if not prov:
            return {"verdict": "reject",
                    "reason": f"experiment '{exp}' has no committed provenance to verify"}
        return {"verdict": "accept", "source_supported": True,
                "reason": "verified by committed experiment provenance"}
    record = {"subject": subj, "predicate": predicate, "object": obj,
              "evidence": [{"source": source, "direction": "supports"}]}
    return critic.criticize(record, abstract=abstract)


def _consensus_status(subj: str, obj: str, predicate: str):
    recs = [r for r in kg_writer.query(subj, obj)
            if r["predicate"].lower() == predicate.lower()]
    if not recs:
        return None
    g = kg.check_connection(recs[0]["subject"], recs[0]["object"])
    return confidence.score_association(
        kg_writer.to_association(recs[0]), prior=confidence.grounding_prior(g)).status


def contribute(subject: str, predicate: str, object: str, source: str = "",
               direction: str = "supports", source_kind: str = "literature",
               sample_size=None, effect_size=None, p_value=None, risk_of_bias=None,
               abstract=None) -> str:
    """Contribute one finding to shared consensus (critic-gated, attributed, routed)."""
    who = _contributor()
    s_norm, o_norm = kg.normalize_entity(subject), kg.normalize_entity(object)
    subj = s_norm["name"] if s_norm else subject.strip()
    obj = o_norm["name"] if o_norm else object.strip()

    verdict = _critic_gate(subj, predicate, obj, source, source_kind, abstract)
    cur = _consensus_status(subj, obj, predicate)          # conservative routing
    if verdict.get("verdict") == "reject":
        status = "rejected"
    elif cur is None:
        status = "pending_review"                          # novel → human
    elif direction == "supports" and cur == "supported" and verdict.get("verdict") == "accept":
        status = "auto_merged"                             # corroborates supported edge
    else:
        status = "pending_review"                          # contradictory / status-shifting → human

    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "contributor": who,
             "subject": subj, "predicate": predicate, "object": obj, "direction": direction,
             "source": source, "source_kind": source_kind, "sample_size": sample_size,
             "effect_size": effect_size, "p_value": p_value, "risk_of_bias": risk_of_bias,
             "critic": verdict.get("verdict"), "status": status}
    CONTRIB_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CONTRIB_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    if status == "auto_merged":                            # merge into consensus + aggregate
        kg_writer.add_association(
            subj, predicate, obj, source=source, direction=direction,
            sample_size=sample_size, effect_size=effect_size, p_value=p_value,
            risk_of_bias=risk_of_bias,
            subject_id=s_norm["id"] if s_norm else None,
            object_id=o_norm["id"] if o_norm else None)

    msg = f"contribution by {who}: {subj} —{predicate}→ {obj}  [{status}, critic={verdict.get('verdict')}]"
    if status == "pending_review":
        msg += "\n  novel/contradictory → held for peer review (shared WIP, not yet consensus)"
    elif status == "rejected":
        msg += f"\n  rejected: {str(verdict.get('reason', ''))[:90]}"
    elif status == "auto_merged":
        msg += "\n  corroborates a supported edge → merged into consensus; confidence updated"
    return msg


def review_queue() -> str:
    """Show contributions awaiting peer review (novel/contradictory), by contributor."""
    if not CONTRIB_LOG.exists():
        return "No contributions yet."
    pend = [json.loads(l) for l in CONTRIB_LOG.open(encoding="utf-8")
            if l.strip() and json.loads(l).get("status") == "pending_review"]
    if not pend:
        return "Review queue empty (nothing pending)."
    lines = [f"Peer-review queue ({len(pend)} pending):"]
    for e in pend[-20:]:
        lines.append(f"  [{e['contributor']}] {e['subject']} —{e['predicate']}→ {e['object']}"
                     f"  (src {e['source']}, {e['source_kind']}, critic={e['critic']})")
    return "\n".join(lines)
