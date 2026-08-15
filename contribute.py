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

The literature critic can be the THINKER, not the local model: pass `critic_verdict` (a
verdict from the client's Claude) and the substrate records it WITHOUT running an LLM —
consensus is gated by Claude, the local model is only the fallback. `critic_by`
(thinker | local | provenance) is logged so every gate decision is attributable.

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
import store_lock

ROOT = Path(__file__).parent
CONTRIB_LOG = ROOT / "memory" / "lab_contributions.jsonl"


def _contributor() -> str:
    return os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "unknown"


def _normalize_verdict(v) -> dict:
    """Coerce a THINKER-supplied critic verdict into the critic's dict shape. Accepts a dict
    ({'verdict','reason','source_supported'}) or a bare 'accept'/'reject' string. Anything not
    explicitly 'accept' is treated as 'reject' — fail-closed, so a malformed verdict can't
    slip junk into consensus."""
    if isinstance(v, str):
        v = {"verdict": v}
    verdict = "accept" if str(v.get("verdict", "")).strip().lower() == "accept" else "reject"
    return {"verdict": verdict,
            "reason": v.get("reason", "supplied by external thinker"),
            "source_supported": bool(v.get("source_supported", verdict == "accept")),
            "well_formed": bool(v.get("well_formed", True))}


def _critic_gate(subj: str, predicate: str, obj: str, source: str,
                 source_kind: str, abstract, supplied=None) -> dict:
    """Experiment findings are verified by committed provenance; literature by a critic
    re-reading the cited abstract.

    THINKER OVERRIDE: if `supplied` is given (a verdict from the client's model — Claude),
    it is used for the literature gate INSTEAD of the local model, so the substrate never has
    to run an LLM to reach consensus. The local critic is only the fallback. (Experiment
    findings still go through the deterministic provenance check — that's a substrate
    integrity invariant, not a thinking task, so it isn't overridable.)"""
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
    if supplied is not None:                       # thinker (Claude/client) is the critic
        return _normalize_verdict(supplied)
    record = {"subject": subj, "predicate": predicate, "object": obj,
              "evidence": [{"source": source, "direction": "supports"}]}
    return critic.criticize(record, abstract=abstract)   # local model = fallback


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
               abstract=None, critic_verdict=None, contributor=None) -> str:
    """Contribute one finding to shared consensus (critic-gated, attributed, routed).

    `critic_verdict` lets the THINKER (the client's model — Claude) supply the literature
    critic judgment ('accept'/'reject' or a dict), so consensus is gated by Claude and the
    substrate stays LLM-free; if omitted, the local critic runs as fallback. The gate's
    origin is recorded as `critic_by` (thinker | local | provenance) for audit.
    `contributor` is the per-request identity (from the caller's auth over the shared HTTP
    deployment); if omitted, falls back to SUBSTRATE_CONTRIBUTOR/$USER (fine for local stdio)."""
    who = contributor or _contributor()
    s_norm, o_norm = kg.normalize_entity(subject), kg.normalize_entity(object)
    subj = s_norm["name"] if s_norm else subject.strip()
    obj = o_norm["name"] if o_norm else object.strip()

    verdict = _critic_gate(subj, predicate, obj, source, source_kind, abstract,
                           supplied=critic_verdict)
    critic_by = ("provenance" if source_kind == "experiment"
                 else "thinker" if critic_verdict is not None else "local")
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
             "critic": verdict.get("verdict"), "critic_by": critic_by, "status": status}
    store_lock.append_jsonl(CONTRIB_LOG, entry)            # locked append (shared-safe)

    if status == "auto_merged":                            # merge into consensus + aggregate
        kg_writer.add_association(
            subj, predicate, obj, source=source, direction=direction,
            sample_size=sample_size, effect_size=effect_size, p_value=p_value,
            risk_of_bias=risk_of_bias,
            subject_id=s_norm["id"] if s_norm else None,
            object_id=o_norm["id"] if o_norm else None)

    msg = (f"contribution by {who}: {subj} —{predicate}→ {obj}  "
           f"[{status}, critic={verdict.get('verdict')} by {critic_by}]")
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
                     f"  (src {e['source']}, {e['source_kind']}, "
                     f"critic={e['critic']} by {e.get('critic_by', 'local')})")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Graduation: a distilled/curated edge corroborated by many independent sources #
# earns a proposal into GATED consensus (the evidence layer -> consensus tier). #
# --------------------------------------------------------------------------- #
def _edge_sources(rec: dict) -> set:
    return {ev.get("source") for ev in rec.get("evidence", []) if ev.get("source")}


def _already_contributed(subj: str, pred: str, obj: str) -> bool:
    if not CONTRIB_LOG.exists():
        return False
    for l in CONTRIB_LOG.open(encoding="utf-8"):
        if not l.strip():
            continue
        e = json.loads(l)
        if (e["subject"].lower() == subj.lower() and e["predicate"].lower() == pred.lower()
                and e["object"].lower() == obj.lower()):
            return True
    return False


def graduation_candidates(min_sources: int = 3) -> str:
    """Curated/distilled edges (kg_writer) backed by >= min_sources INDEPENDENT sources that
    aren't in the consensus pipeline yet — well-corroborated enough to PROPOSE to gated consensus.
    Independence groups PMIDs by last-author, so one group citing itself doesn't inflate the count."""
    import deep_search
    cands = []
    for r in kg_writer._load():
        srcs = _edge_sources(r)                                  # cheap pre-filter: distinct sources
        if len(srcs) < min_sources or _already_contributed(r["subject"], r["predicate"], r["object"]):
            continue
        indep = deep_search.independent_count(srcs)              # network, only on pre-filtered few
        if indep >= min_sources:
            cands.append((r, indep, len(srcs)))
    if not cands:
        return (f"No graduation candidates (need >= {min_sources} INDEPENDENT sources — grouped by "
                "last-author — and not already contributed). Keep distilling; edges accrue evidence.")
    cands.sort(key=lambda x: -x[1])
    out = [f"{len(cands)} edge(s) corroborated by >= {min_sources} INDEPENDENT sources — ready to "
           "PROPOSE to consensus:"]
    for r, indep, total in cands[:15]:
        out.append(f"  {r['subject']} —{r['predicate']}→ {r['object']}  "
                   f"({indep} independent of {total} sources)")
    out.append("Graduate one with graduate(subject, predicate, object, critic_verdict='accept') — "
               "it routes through the critic gate (novel → peer review; corroborating → auto-merge).")
    return "\n".join(out)


def graduate(subject: str, predicate: str, object: str, critic_verdict=None,
             contributor=None) -> str:
    """Graduate a well-corroborated distilled edge from the literature-EVIDENCE layer into GATED
    consensus — routes it through contribute() with the INDEPENDENT corroboration as its source."""
    import deep_search
    recs = [r for r in kg_writer.query(subject, object)
            if r["predicate"].lower() == predicate.lower()]
    if not recs:
        return f"No curated edge {subject} —{predicate}→ {object} to graduate."
    srcs = _edge_sources(recs[0])
    indep = deep_search.independent_count(srcs)
    return contribute(subject, predicate, object,
                      source=f"distilled evidence: {indep} independent source(s) (of {len(srcs)})",
                      source_kind="literature", critic_verdict=critic_verdict,
                      contributor=contributor)
