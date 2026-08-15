"""deadends — the lab's NEGATIVE knowledge: what was tried and didn't work, queryable at intake.

A lab brain that only remembers successes lets the lab repeat failed effort. This is the
graveyard: refuted links, abandoned hypotheses, overturned beliefs, invalid pipelines, and
explicit "we tried X, it failed, here's why" notes — surfaced BEFORE someone commits to a
hypothesis, so a dead end is a warning, not a rediscovery.

Two sources, one shape:
  - HARVESTED (derived on read, always in sync with the substrate):
      * well-powered REFUTED consensus edges (confidence status `refuted`);
      * ABANDONED hypotheses (status: abandoned);
      * OVERTURNED contradictions (an adjudication that killed a belief, ADR-0053);
      * failed HALT validity gates (an experiment ruled INVALID — a pipeline/cohort dead end).
  - EXPLICIT: `record_dead_end(...)` for a human "we tried this and it didn't pan out".

The load-bearing distinction (borrowed from `confidence.py`): **evidenced** vs **soft**. An
UNDERPOWERED null is NOT a dead end — absence of evidence ≠ evidence of absence — so it's flagged
revisit-worthy, never "avoid". `check()` at intake calibrates its warning accordingly. Read-only
over the existing logs; the only write is the explicit append-only store.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import store_lock

ROOT = Path(__file__).parent
MEM = ROOT / "memory"
STORE = MEM / "dead_ends.jsonl"             # explicit records (append-only)
HYP = ROOT / "hypotheses"
EXP = ROOT / "experiments"

# reason → strength. Evidenced dead ends warrant "avoid / needs a different approach"; soft ones
# ("looked negative but thin", set aside) are revisit-worthy, not disqualifying.
_EVIDENCED_REASONS = {"refuted", "overturned", "invalid", "not_reproducible", "confounded"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _contributor() -> str:
    return os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "unknown"


def _strength(reason: str) -> str:
    return "evidenced" if reason in _EVIDENCED_REASONS else "soft"


@dataclass
class DeadEnd:
    subject: str
    object: str | None
    approach: str | None        # the method/design that failed, if the dead end is approach-level
    reason: str                 # refuted | overturned | invalid | abandoned | underpowered | …
    why: str                    # human-readable explanation
    strength: str               # "evidenced" | "soft"
    source: str                 # provenance tag (curated_kg | H0xx | contradiction:id | reported)
    contributor: str | None = None
    ts: str | None = None
    revisit_if: str | None = None


# --------------------------------------------------------------------------- #
# Harvest — derive dead ends from existing structured negative signals.        #
# --------------------------------------------------------------------------- #
def _harvest_refuted() -> list:
    """Well-powered REFUTED consensus edges. Excludes `promising_but_poorly_tested` /
    `under_investigated` — those are re-test recommendations, the opposite of a dead end."""
    import beliefs
    import kg_writer
    out = []
    for r in kg_writer._load():
        snap = beliefs.snapshot(r["subject"], r["predicate"], r["object"])
        if snap and snap.status == "refuted":
            out.append(DeadEnd(
                r["subject"], r["object"], r["predicate"], "refuted",
                f"well-powered null(s) refute this link (confidence {snap.confidence:.2f})",
                "evidenced", "curated_kg", ts=None))
    return out


def _harvest_abandoned() -> list:
    """Hypotheses explicitly abandoned."""
    out = []
    try:
        import yaml
    except Exception:
        return out
    for f in (HYP.glob("*.y*ml") if HYP.exists() else []):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if str(d.get("status", "")).lower() == "abandoned":
            out.append(DeadEnd(
                str(d.get("id", f.stem)), None, str(d.get("method", ""))[:120] or None,
                "abandoned", f"hypothesis abandoned: {str(d.get('title', ''))[:120]}",
                "soft", str(d.get("id", f.stem)), ts=str(d.get("created")) or None,
                revisit_if="new data or a materially different method"))
    return out


def _harvest_overturned() -> list:
    """Beliefs killed by adjudication — a resolved contradiction with resolution `overturned`."""
    import beliefs
    events = beliefs._contra_events()
    opens = {e["id"]: e for e in events if e.get("event") == "open"}
    out = []
    for e in events:
        if e.get("event") == "resolve" and e.get("resolution") == "overturned":
            o = opens.get(e["id"])
            if not o:
                continue
            out.append(DeadEnd(
                o.get("subject", "?"), o.get("object"), o.get("predicate"), "overturned",
                f"belief overturned in adjudication (conflict {e['id']})",
                "evidenced", f"contradiction:{e['id']}",
                contributor=e.get("by"), ts=e.get("ts")))
    return out


def _harvest_invalid_gates() -> list:
    """Experiments ruled INVALID by a failed HALT validity gate — a pipeline/cohort dead end."""
    out = []
    for vj in (EXP.glob("*/validity.json") if EXP.exists() else []):
        try:
            gates = json.loads(vj.read_text(encoding="utf-8"))
        except Exception:
            continue
        hid = vj.parent.name
        for g in gates:
            if not g.get("passed", True) and g.get("severity") == "halt":
                out.append(DeadEnd(
                    hid, None, g.get("name"), "invalid",
                    f"HALT gate '{g.get('name')}' failed — experiment INVALID: {g.get('detail', '')}",
                    "evidenced", f"experiment:{hid}", ts=None,
                    revisit_if="the cohort/pipeline defect is fixed and the run repeated"))
    return out


def _explicit() -> list:
    out = []
    if STORE.exists():
        for line in STORE.open(encoding="utf-8"):
            if line.strip():
                d = json.loads(line)
                out.append(DeadEnd(**{k: d.get(k) for k in DeadEnd.__dataclass_fields__}))
    return out


def all_dead_ends() -> list:
    """Every dead end — explicit + harvested — evidenced first, then most recent."""
    des = (_explicit() + _harvest_refuted() + _harvest_abandoned()
           + _harvest_overturned() + _harvest_invalid_gates())
    return sorted(des, key=lambda d: (d.strength != "evidenced", d.ts or ""))


# --------------------------------------------------------------------------- #
# Record + query.                                                              #
# --------------------------------------------------------------------------- #
_REASONS = ("refuted", "overturned", "invalid", "not_reproducible", "confounded",
            "abandoned", "underpowered", "infeasible", "set_aside", "other")


def record_dead_end(subject: str, object: str = "", approach: str = "", reason: str = "other",
                    why: str = "", revisit_if: str = "", contributor=None) -> str:
    """Record an explicit dead end — 'we tried this and it didn't work'. `reason` in
    {refuted, overturned, invalid, not_reproducible, confounded, abandoned, underpowered,
    infeasible, set_aside, other}; strength (evidenced vs soft) is inferred from it. Attributed,
    append-only, SHARED — the point is that the whole lab stops repeating the effort."""
    reason = reason.strip().lower()
    if reason not in _REASONS:
        return f"reason must be one of {list(_REASONS)} (got {reason!r})."
    de = {"subject": subject.strip(), "object": object.strip() or None,
          "approach": approach.strip() or None, "reason": reason, "why": why.strip(),
          "strength": _strength(reason), "source": "reported",
          "contributor": contributor or _contributor(), "ts": _now(),
          "revisit_if": revisit_if.strip() or None}
    store_lock.append_jsonl(STORE, de)
    tag = "evidenced" if de["strength"] == "evidenced" else "soft (revisit-worthy)"
    tgt = de["subject"] + (f" — {de['object']}" if de["object"] else "")
    return f"dead end recorded [{reason}, {tag}]: {tgt}"


def _ci(a: str, b: str) -> bool:
    """Forgiving case-insensitive entity match: equal or one contains the other (len>2)."""
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    return bool(a) and bool(b) and (a == b or (len(a) > 2 and len(b) > 2 and (a in b or b in a)))


def _norm(e: str) -> str:
    if not e:
        return e
    try:
        import kg_memory as kg
        r = kg.normalize_entity(e)
        return r["name"] if r else e
    except Exception:
        return e


def check(subject: str, object: str = "", approach: str = "", normalize: bool = True) -> list:
    """Dead ends relevant to a candidate line of work, as (DeadEnd, match_kind) pairs.
    match_kind: 'pair' (both entities hit a recorded dead end), 'entity' (one entity does),
    'approach' (the method matches). Evidenced + pair matches first."""
    a = _norm(subject) if normalize else subject
    b = _norm(object) if normalize else object
    q = [x for x in (a, b) if x]
    hits = []
    for de in all_dead_ends():
        ents = [x for x in (de.subject, de.object) if x]
        kind = None
        if len(q) == 2 and len(ents) == 2 and \
                all(any(_ci(x, y) for y in ents) for x in q):
            kind = "pair"
        elif any(_ci(x, y) for x in q for y in ents):
            kind = "entity"
        elif approach and de.approach and approach.strip().lower() in de.approach.lower():
            kind = "approach"
        if kind:
            hits.append((de, kind))
    order = {"pair": 0, "entity": 1, "approach": 2}
    return sorted(hits, key=lambda h: (h[0].strength != "evidenced", order[h[1]]))


def _fmt(de: DeadEnd, kind: str) -> str:
    if de.object:
        link = f" —{de.approach}→ " if de.approach else " ↔ "
        tgt = f"{de.subject}{link}{de.object}"
    elif de.approach:
        tgt = f"{de.subject}  (approach: {de.approach})"
    else:
        tgt = de.subject
    by = f", {de.contributor}" if de.contributor else ""
    tail = f"  ↻ revisit if {de.revisit_if}" if de.revisit_if else ""
    return (f"[{de.strength}/{de.reason}] {tgt} — {de.why} "
            f"(src {de.source}{by})" + tail)


def render_check(subject: str, object: str = "", approach: str = "") -> str:
    """Intake warning: '' if clear, else a calibrated heads-up (evidenced = avoid; soft =
    revisit-worthy). Meant to be shown when someone is about to commit to a line of work."""
    hits = check(subject, object, approach)
    if not hits:
        return ""
    evidenced = [h for h in hits if h[0].strength == "evidenced"]
    head = ("⛔ PRIOR DEAD END — this line has been tried and ruled out:" if evidenced
            else "⚠ Heads up — a related avenue was set aside (not disqualifying):")
    lines = [head] + [f"  • {_fmt(de, kind)}" for de, kind in hits[:5]]
    if evidenced:
        lines.append("  → Don't just repeat it: use a materially different approach, or address "
                     "the specific reason above before committing.")
    else:
        lines.append("  → Worth a look, but the earlier attempt was soft/underpowered — a better-"
                     "powered or redesigned test may still be worthwhile.")
    return "\n".join(lines)


def render_list() -> str:
    """The whole graveyard — the lab's negative knowledge in one place."""
    des = all_dead_ends()
    if not des:
        return ("No dead ends recorded yet. They accrue automatically (refuted edges, abandoned "
                "hypotheses, overturned beliefs, invalid runs) or explicitly (record_dead_end).")
    ev = [d for d in des if d.strength == "evidenced"]
    soft = [d for d in des if d.strength == "soft"]
    out = [f"Dead-end store — {len(des)} entr(ies): {len(ev)} evidenced, {len(soft)} soft.", ""]
    if ev:
        out.append("EVIDENCED (tried and ruled out):")
        out += [f"  • {_fmt(d, '')}" for d in ev[:20]]
    if soft:
        out.append("\nSOFT (set aside / thin — revisit-worthy):")
        out += [f"  • {_fmt(d, '')}" for d in soft[:20]]
    return "\n".join(out)


if __name__ == "__main__":
    # Hermetic demo: isolate the store, stub the harvest signals, and show record + intake check.
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    STORE = tmp / "dead_ends.jsonl"
    globals()["_harvest_refuted"] = lambda: [DeadEnd(
        "IL6", "Alzheimer's disease", "associates", "refuted",
        "three well-powered nulls (conf 0.12)", "evidenced", "curated_kg")]
    globals()["_harvest_abandoned"] = lambda: [DeadEnd(
        "H007", None, "bulk RNA-seq differential expression", "abandoned",
        "hypothesis abandoned: retinal splicing panel underpowered", "soft", "H007",
        revisit_if="single-nucleus data becomes available")]
    globals()["_harvest_overturned"] = lambda: []
    globals()["_harvest_invalid_gates"] = lambda: []

    print(record_dead_end("MYOC", "open-angle glaucoma", approach="candidate-gene assoc",
                          reason="not_reproducible", why="failed to replicate in 2 cohorts",
                          contributor="alice"))
    print(record_dead_end("polygenic score", "intraocular pressure", reason="set_aside",
                          why="parked pending a larger PRS training set", contributor="bob"))
    print()
    print("=== list ===")
    print(render_list())
    print("\n=== intake check: IL6 ↔ Alzheimer's (evidenced pair → avoid) ===")
    print(render_check("IL6", "Alzheimer's disease") or "(clear)")
    print("\n=== intake check: polygenic score ↔ IOP (soft pair → revisit-worthy) ===")
    print(render_check("polygenic score", "intraocular pressure") or "(clear)")
    print("\n=== intake check: TP53 ↔ melanoma (clear) ===")
    print(render_check("TP53", "melanoma") or "(clear)")
