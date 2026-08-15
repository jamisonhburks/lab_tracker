"""beliefs — the lab's belief as LIVING STATE (the belief lifecycle).

`confidence.py` answers "given this edge's evidence, how strongly should we believe it
*right now*?" — a stateless projection. This module makes that projection **stateful**, so
the substrate reads like a lab brain whose knowledge updates:

  1. PERSISTED belief per edge — the lab's current confidence + status, materialized so
     "what do we believe about X?" is a lookup, not a recomputation.
  2. INCREMENTAL revision — every contribution that changes an edge's evidence re-scores it
     and records the DELTA ("0.48 → 0.61, +0.13, because DisGeNET corroborated"). This one
     behavior is what makes the knowledge feel alive rather than static.
  3. A belief TRAJECTORY — an append-only trail of every revision. It is both the "updating
     knowledge" history AND the provenance of the confidence itself (why is it 0.61 — here is
     the exact sequence of evidence that moved it).
  4. A CONTRADICTION LEDGER — when a new claim OPPOSES an established belief, the tension is
     kept as a first-class, resolvable object (both sides preserved) instead of silently
     gated away. The substrate only RECORDS the conflict; a thinker resolves it (ADR-0040).

Design notes:
  - No new epistemics. Belief is `confidence.score_association()` over the authoritative,
    accumulated evidence in `kg_writer`, plus the KG grounding prior — exactly what
    `query_curated_findings` shows. This module only persists and diffs that projection.
  - Event-sourced, append-only, `store_lock`-guarded — the same shared-safe, auditable ethos
    as the contribution log. State is a fold over the log, so history is never rewritten.
  - Read-mostly and cheap; the writer hooks live in `contribute.py` (two small calls).
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import confidence
import kg_memory as kg
import kg_writer
import store_lock

ROOT = Path(__file__).parent
BELIEF_LOG = ROOT / "memory" / "belief_log.jsonl"       # append-only belief trajectory
CONTRA_LOG = ROOT / "memory" / "contradictions.jsonl"   # append-only contradiction ledger

# Minimum confidence move worth recording as a distinct revision (below this, and with no
# status change, the evidence didn't meaningfully shift belief — don't clutter the trail).
_EPS = 0.005

# Established leanings — the only statuses strong enough for an opposing claim to count as a
# genuine CONTRADICTION. "contested"/"under_investigated" have no settled position to oppose;
# a new opposing study there is just more evidence accumulating, not a conflict.
_POSITIVE_LEAN = {"supported"}
_NEGATIVE_LEAN = {"refuted"}


def _key(subject: str, predicate: str, object: str) -> str:
    return f"{subject.strip().lower()}|{predicate.strip().lower()}|{object.strip().lower()}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Belief as a live projection over the authoritative (accumulated) evidence.   #
# --------------------------------------------------------------------------- #
@dataclass
class BeliefSnapshot:
    """The lab's belief in one edge, projected from its current evidence + KG grounding."""
    subject: str
    predicate: str
    object: str
    confidence: float
    status: str
    support: float
    refute: float
    investigation: float
    n_evidence: int
    grounding: str


def _find_record(subject: str, predicate: str, object: str) -> dict | None:
    """The curated-KG record for this exact edge (case-insensitive), or None if untracked."""
    for r in kg_writer._load():
        if (r["subject"].strip().lower() == subject.strip().lower()
                and r["predicate"].strip().lower() == predicate.strip().lower()
                and r["object"].strip().lower() == object.strip().lower()):
            return r
    return None


def snapshot(subject: str, predicate: str, object: str) -> BeliefSnapshot | None:
    """Compute the CURRENT belief in an edge live from `kg_writer` evidence + KG grounding —
    the same projection `query_curated_findings` renders. None if the edge isn't in the
    curated KG yet (nothing to believe)."""
    rec = _find_record(subject, predicate, object)
    if rec is None:
        return None
    g = kg.check_connection(rec["subject"], rec["object"])
    res = confidence.score_association(kg_writer.to_association(rec),
                                       prior=confidence.grounding_prior(g))
    return BeliefSnapshot(rec["subject"], rec["predicate"], rec["object"],
                          res.confidence, res.status, res.support, res.refute,
                          res.investigation, len(rec.get("evidence", [])), g)


# --------------------------------------------------------------------------- #
# The trajectory: append-only belief_log; state is the last event per edge.    #
# --------------------------------------------------------------------------- #
def _events(key: str | None = None) -> list:
    if not BELIEF_LOG.exists():
        return []
    out = []
    for line in BELIEF_LOG.open(encoding="utf-8"):
        if not line.strip():
            continue
        e = json.loads(line)
        if key is None or e.get("key") == key:
            out.append(e)
    return out


def _last_event(key: str) -> dict | None:
    evs = _events(key)
    return evs[-1] if evs else None


def revise(subject: str, predicate: str, object: str, trigger: dict | None = None,
           prev: BeliefSnapshot | None = None) -> dict | None:
    """Re-score an edge after its evidence changed and RECORD the revision if belief moved.

    `prev` is the belief BEFORE the triggering evidence landed (capture it before writing the
    new evidence for an accurate delta on the very first touch); if omitted, the last logged
    event is used as the baseline. `trigger` attributes the move (contributor / source / kind
    / contribution_status). Returns the appended event, or None if there was nothing to score
    or belief didn't meaningfully change."""
    now = snapshot(subject, predicate, object)
    if now is None:
        return None

    key = _key(subject, predicate, object)
    prior_conf = prev.confidence if prev is not None else None
    prior_status = prev.status if prev is not None else None
    if prior_conf is None:                                   # fall back to logged baseline
        last = _last_event(key)
        if last is not None:
            prior_conf, prior_status = last["confidence"], last["status"]

    delta = None if prior_conf is None else round(now.confidence - prior_conf, 3)
    changed = (prior_conf is None or prior_status != now.status or abs(delta or 0.0) >= _EPS)
    if not changed:
        return None

    event = {"ts": _now(), "key": key, "subject": now.subject, "predicate": now.predicate,
             "object": now.object, "confidence": now.confidence, "status": now.status,
             "prev_confidence": prior_conf, "prev_status": prior_status, "delta": delta,
             "support": now.support, "refute": now.refute, "investigation": now.investigation,
             "n_evidence": now.n_evidence, "grounding": now.grounding,
             "trigger": trigger or {}}
    store_lock.append_jsonl(BELIEF_LOG, event)
    return event


def current(subject: str, predicate: str, object: str) -> dict | None:
    """The lab's CURRENT belief in an edge: the last recorded revision, or a fresh snapshot if
    the edge exists but hasn't been revised through the lifecycle yet. None if untracked."""
    last = _last_event(_key(subject, predicate, object))
    if last is not None:
        return last
    snap = snapshot(subject, predicate, object)
    return None if snap is None else {**asdict(snap), "delta": None, "prev_confidence": None,
                                      "prev_status": None, "trigger": {}, "ts": None}


def _arrow(delta) -> str:
    if delta is None:
        return "•"
    return "▲" if delta > 0 else "▼" if delta < 0 else "→"


def render_current(subject: str, predicate: str, object: str) -> str:
    """One-glance view of an edge's current belief and how it last moved."""
    b = current(subject, predicate, object)
    if b is None:
        return (f"No belief tracked for {subject} —{predicate}→ {object} "
                "(not in the curated KG yet).")
    d = b.get("delta")
    move = "" if d is None else f" {_arrow(d)} {d:+.2f} on last update"
    trig = b.get("trigger") or {}
    who = trig.get("contributor")
    prov = (f" — last update by {who}" + (f" ({trig['source']})" if trig.get("source") else "")
            ) if who else ""
    ts = f" · {b['ts'][:10]}" if b.get("ts") else ""
    return (f"{b['subject']} —{b['predicate']}→ {b['object']}\n"
            f"  belief {b['confidence']:.2f} ({b['status']}){move}\n"
            f"  {b.get('n_evidence', '?')} evidence · KG:{b.get('grounding', '?')}{ts}{prov}")


def render_history(subject: str, predicate: str, object: str) -> str:
    """The full belief TRAJECTORY for an edge — the sequence of evidence that moved it."""
    evs = _events(_key(subject, predicate, object))
    if not evs:
        return (f"No belief history for {subject} —{predicate}→ {object} yet "
                "(it hasn't accrued a revision through the lifecycle).")
    spark = "→".join(f"{e['confidence']:.2f}" for e in evs)
    net = evs[-1]["confidence"] - (evs[0]["prev_confidence"]
                                   if evs[0].get("prev_confidence") is not None
                                   else evs[0]["confidence"])
    lines = [f"Belief trajectory — {evs[0]['subject']} —{evs[0]['predicate']}→ {evs[0]['object']}",
             f"  {spark}   ({evs[-1]['status']}, net {net:+.2f} over {len(evs)} update(s))"]
    for e in evs:
        trig = e.get("trigger") or {}
        by = trig.get("contributor", "?")
        src = f" {trig['source']}" if trig.get("source") else ""
        d = e.get("delta")
        dtxt = f"{_arrow(d)} {d:+.2f}" if d is not None else "• baseline"
        lines.append(f"  {e['ts'][:10]}  {e['confidence']:.2f} ({e['status']})  {dtxt}"
                     f"  ← {by}{src}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The contradiction ledger: opposing claims kept side-by-side, thinker-resolved #
# --------------------------------------------------------------------------- #
def _is_contradiction(incoming_direction: str, current_status: str) -> bool:
    """A genuine conflict: the incoming claim OPPOSES an ESTABLISHED belief. A refuting claim
    against a supported edge (or a supporting claim against a refuted one). Edges with no
    settled leaning (contested/under_investigated) just accumulate evidence — not a conflict."""
    d, s = incoming_direction.strip().lower(), current_status.strip().lower()
    return ((d == "refutes" and s in _POSITIVE_LEAN)
            or (d == "supports" and s in _NEGATIVE_LEAN))


def _contra_events() -> list:
    if not CONTRA_LOG.exists():
        return []
    return [json.loads(l) for l in CONTRA_LOG.open(encoding="utf-8") if l.strip()]


def register_contradiction(subject: str, predicate: str, object: str, incoming_direction: str,
                           current_status: str, incoming: dict | None = None) -> dict | None:
    """If an incoming claim genuinely OPPOSES the established belief, open a conflict in the
    ledger (both sides preserved, state=unresolved) and return it. Returns None when it isn't a
    real contradiction — e.g. corroborating evidence merely held for conservative review — so
    the caller can pass every held contribution through and let this decide."""
    if not _is_contradiction(incoming_direction, current_status):
        return None
    key = _key(subject, predicate, object)
    n = sum(1 for e in _contra_events() if e.get("event") == "open" and e.get("key") == key)
    cid = f"{key}#{n + 1}"
    est = current(subject, predicate, object) or {}
    event = {"ts": _now(), "event": "open", "id": cid, "key": key,
             "subject": subject, "predicate": predicate, "object": object,
             "established": {"status": current_status,
                             "confidence": est.get("confidence"),
                             "n_evidence": est.get("n_evidence")},
             "incoming": {"direction": incoming_direction, **(incoming or {})},
             "state": "unresolved"}
    store_lock.append_jsonl(CONTRA_LOG, event)
    return event


def open_conflicts() -> list:
    """Fold the ledger to the currently UNRESOLVED conflicts (opens minus resolves)."""
    resolved = {e["id"] for e in _contra_events() if e.get("event") == "resolve"}
    return [e for e in _contra_events()
            if e.get("event") == "open" and e["id"] not in resolved]


def render_conflicts() -> str:
    """The open contradiction ledger — where the lab's knowledge is genuinely in tension."""
    conf = open_conflicts()
    if not conf:
        return "No open contradictions — the consensus KG has no unresolved conflicts."
    lines = [f"Open contradictions ({len(conf)}) — established belief vs. an opposing claim:"]
    for c in conf:
        est = c.get("established", {})
        inc = c.get("incoming", {})
        ec = est.get("confidence")
        lines.append(
            f"  [{c['id']}]  {c['subject']} —{c['predicate']}→ {c['object']}\n"
            f"     established: {est.get('status')}"
            f"{f' (conf {ec:.2f})' if isinstance(ec, (int, float)) else ''}"
            f"  vs.  incoming: {inc.get('direction')}"
            f"{f' from {inc['contributor']}' if inc.get('contributor') else ''}"
            f"{f' ({inc['source']})' if inc.get('source') else ''}")
    lines.append("Resolve one with resolve_conflict(id, resolution=upheld|overturned|"
                 "contested, rationale=...). The substrate records the tension; a thinker judges it.")
    return "\n".join(lines)


_RESOLUTIONS = {"upheld", "overturned", "contested"}


def resolve_conflict(conflict_id: str, resolution: str, by: str = "", rationale: str = "") -> str:
    """Record a THINKER's resolution of an open contradiction (append-only; the open event is
    never rewritten). `resolution`: upheld (established belief stands) | overturned (the incoming
    claim wins) | contested (both genuinely stand — the edge is disputed)."""
    r = resolution.strip().lower()
    if r not in _RESOLUTIONS:
        return f"resolution must be one of {sorted(_RESOLUTIONS)} (got {resolution!r})."
    if conflict_id not in {c["id"] for c in open_conflicts()}:
        return f"No OPEN conflict {conflict_id!r} (already resolved, or never opened)."
    store_lock.append_jsonl(CONTRA_LOG, {"ts": _now(), "event": "resolve", "id": conflict_id,
                                         "resolution": r, "by": by or "unknown",
                                         "rationale": rationale})
    return f"conflict {conflict_id} resolved as {r} by {by or 'unknown'}."


if __name__ == "__main__":
    # Hermetic self-demo: isolate all storage to a temp dir and stub KG grounding, so the demo
    # never touches real memory/ or loads the full KG. Watch a belief rise as evidence accrues,
    # then watch a contradicting claim open a ledger entry.
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    kg_writer.STORE = tmp / "curated_kg.jsonl"
    BELIEF_LOG = tmp / "belief_log.jsonl"
    CONTRA_LOG = tmp / "contradictions.jsonl"
    kg.check_connection = lambda a, b: "off_graph"          # hermetic: no KG load in the demo

    subj, pred, obj = "Gene:5743", "associates", "Disease:DOID:8778"

    print("=== belief updates as independent evidence accrues ===")
    for src in ("GWAS Catalog", "DisGeNET", "OMIM"):
        before = snapshot(subj, pred, obj)
        kg_writer.add_association(subj, pred, obj, source=src, direction="supports", power=0.85)
        ev = revise(subj, pred, obj, prev=before,
                    trigger={"contributor": "demo", "source": src, "kind": "literature",
                             "contribution_status": "auto_merged"})
        if ev and ev["delta"] is not None:
            print(f"  + {src}: {ev['prev_confidence']:.2f} → {ev['confidence']:.2f} "
                  f"({ev['status']}, {ev['delta']:+.2f})")
        elif ev:
            print(f"  + {src}: baseline {ev['confidence']:.2f} ({ev['status']})")
    print()
    print(render_history(subj, pred, obj), "\n")

    print("=== a contradicting claim opens a ledger entry ===")
    c = register_contradiction(subj, pred, obj, incoming_direction="refutes",
                               current_status="supported",
                               incoming={"contributor": "skeptic", "source": "PMID:99999",
                                         "p_value": 0.6, "sample_size": 5000})
    print(f"  opened {c['id']}\n" if c else "  (no contradiction)\n")
    print(render_conflicts())
