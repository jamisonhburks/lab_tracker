"""subscriptions — follow other members and projects; a change digest since you last looked.

A lab member registers interest in a colleague (`member:<name>`) or a project
(`project:<id>`, where <id> is a hypothesis like H001 or a campaign name). Asking for a summary
then surfaces a DELTA of what changed on everything you follow — hypothesis/workflow status,
contributions, belief revisions (ADR-0053), contradictions, and exploratory findings — grouped
by target and attributed.

Reuses existing units — NO new project/ownership schema. "Membership" is inferred from
attribution: a member's projects are the ones their attributed work touches. The digest is
read-heavy over the existing timestamped, attributed logs; the only writes are the per-person
subscription registry (append-only, folded to current state) and a per-person 'last seen'
marker (the same delta mechanism as the warm-start briefing). Surfaces two ways: a dedicated
`digest()` tool, and a compact preview folded into the warm start.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import store_lock

ROOT = Path(__file__).parent
MEM = ROOT / "memory"
SUBS = MEM / "subscriptions.jsonl"          # append-only follow/unfollow events
SEEN = MEM / "subscription_seen.json"       # per-person 'last digest' timestamp
CONTRIB = MEM / "lab_contributions.jsonl"
BELIEF = MEM / "belief_log.jsonl"
CONTRA = MEM / "contradictions.jsonl"
MISC = MEM / "misc_findings.jsonl"
HYP = ROOT / "hypotheses"
CAMP = ROOT / "campaigns"
REPORTS = ROOT / "reports"
EXP = ROOT / "experiments"

_KINDS = ("member", "project")
_CAP = 6                                     # max bullets shown per target


def _who(subscriber) -> str:
    return subscriber or os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "you"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _jsonl(p: Path) -> list:
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()] if p.exists() else []


# --------------------------------------------------------------------------- #
# The registry: append-only follow/unfollow events, folded to current state.   #
# --------------------------------------------------------------------------- #
def _resolve_project(value: str):
    """(kind, display_name, [experiment_ids]) for a project value — a hypothesis id or a
    campaign (by file stem or name). 'unknown' if it matches neither (still followable)."""
    v = value.strip()
    if HYP.exists() and list(HYP.glob(f"{v}*.y*ml")):
        return "hypothesis", v, [v]
    if CAMP.exists():
        for f in CAMP.glob("*.json"):
            try:
                c = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if f.stem == v or c.get("name") == v:
                return "campaign", c.get("name", f.stem), \
                    [n["experiment_id"] for n in c.get("nodes", []) if n.get("experiment_id")]
    return "unknown", v, [v]


def _parse_target(target: str):
    """('member'|'project', value). Accepts 'member:alice' / 'project:H001'; a bare value is
    read as a project when it resolves to one, else a member."""
    t = target.strip()
    if ":" in t:
        kind, val = (p.strip() for p in t.split(":", 1))
        if kind.lower() in _KINDS and val:
            return kind.lower(), val
    return ("project" if _resolve_project(t)[0] != "unknown" else "member"), t


def subscribe(subscriber, target: str) -> str:
    who = _who(subscriber)
    kind, val = _parse_target(target)
    store_lock.append_jsonl(SUBS, {"ts": _now(), "subscriber": who, "action": "subscribe",
                                   "kind": kind, "value": val})
    return f"{who} now follows {kind}:{val}."


def unsubscribe(subscriber, target: str) -> str:
    who = _who(subscriber)
    kind, val = _parse_target(target)
    store_lock.append_jsonl(SUBS, {"ts": _now(), "subscriber": who, "action": "unsubscribe",
                                   "kind": kind, "value": val})
    return f"{who} no longer follows {kind}:{val}."


def subscriptions_of(subscriber) -> list:
    who = _who(subscriber)
    state = {}
    for e in _jsonl(SUBS):
        if e.get("subscriber") == who:
            state[(e["kind"], e["value"])] = e["action"]      # last action per target wins
    return [k for k, action in state.items() if action == "subscribe"]


def list_subscriptions(subscriber) -> str:
    subs = subscriptions_of(subscriber)
    if not subs:
        return ("You follow nothing yet. Try follow('member:alice') or follow('project:H001') "
                "(a hypothesis id or a campaign name).")
    return "You follow:\n" + "\n".join(f"  • {kind}:{val}" for kind, val in subs)


def known_members() -> list:
    """All lab members: the profile ROSTER unioned with anyone who has attributed work or a
    subscription. The roster is what makes colleagues followable on day 1 (before attribution
    exists); the union keeps late-joiners and non-roster contributors discoverable too."""
    names = set()
    try:
        import lab_profile
        names.update(lab_profile.roster())
    except Exception:
        pass
    for r in _jsonl(CONTRIB) + _jsonl(MISC):
        if r.get("contributor"):
            names.add(r["contributor"])
    for e in _jsonl(SUBS):
        if e.get("subscriber"):
            names.add(e["subscriber"])
    return sorted(names)


def list_members(subscriber=None) -> str:
    """The lab roster — who you can follow — marking yourself and anyone you already follow."""
    who = _who(subscriber)
    members = known_members()
    if not members:
        return ("No lab members known yet — add a `members:` roster to profiles/<lab>.yaml so "
                "colleagues are followable before they've contributed.")
    following = {val for kind, val in subscriptions_of(subscriber) if kind == "member"}
    lines = [f"Lab members ({len(members)}):"]
    for m in members:
        tag = "  ← you" if m == who else "  (following)" if m in following else ""
        lines.append(f"  • {m}{tag}")
    lines.append("Follow one with follow('member:<name>').")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The delta: what changed on a followed target since `since`.                  #
# --------------------------------------------------------------------------- #
def _seen(who):
    try:
        return json.loads(SEEN.read_text(encoding="utf-8")).get(who)
    except Exception:
        return None


def _mark_seen(who, ts):
    d = {}
    try:
        d = json.loads(SEEN.read_text(encoding="utf-8"))
    except Exception:
        pass
    d[who] = ts
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    try:
        SEEN.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def _newer(rows, since):
    return [r for r in rows if not since or r.get("ts", "") > since]


def _project_entities(exp_ids) -> set:
    """Best-effort entities a project is about — from a hypothesis' `subject`/`object`/`entities`
    fields, if present. Empty when the spec doesn't declare them (then project matching relies on
    experiment-id linkage alone)."""
    try:
        import yaml
    except Exception:
        return set()
    ents = set()
    for hid in exp_ids:
        for f in (HYP.glob(f"{hid}*.y*ml") if HYP.exists() else []):
            try:
                d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            for k in ("subject", "object"):
                if isinstance(d.get(k), str):
                    ents.add(d[k].strip().lower())
            if isinstance(d.get("entities"), list):
                ents.update(str(x).strip().lower() for x in d["entities"])
    return ents


def _hyp_status(hid) -> str:
    try:
        import yaml
        hits = list(HYP.glob(f"{hid}*.y*ml")) if HYP.exists() else []
        d = yaml.safe_load(hits[0].read_text(encoding="utf-8")) or {} if hits else {}
    except Exception:
        d = {}
    stage = ("evaluated" if (REPORTS / f"{hid}_evaluation.md").exists()
             else "implemented/running" if (EXP / hid).exists() else "spec only")
    return f"{hid} {d.get('status', '?')} · {stage}"


def _member_projects(member) -> list:
    """Projects a member is active on — inferred from their experiment-attributed contributions."""
    ids = set()
    for c in _jsonl(CONTRIB):
        if c.get("contributor") == member and c.get("source_kind") == "experiment":
            s = (c.get("source") or "").split(":")[-1].strip()
            if s:
                ids.add(s)
    return sorted(ids)


def _edge(r):
    return f"{r.get('subject', '?')} —{r.get('predicate', '?')}→ {r.get('object', '?')}"


def _ts(r):
    t = r.get("ts", "")
    return f"  ({t[:10]})" if t else ""


def _by(name):
    return f"  ← {name}" if name else ""


def _fmt_contrib(c, who=False):
    return f"contributed {_edge(c)} [{c.get('status', '?')}]" + _ts(c) + \
        (_by(c.get("contributor")) if who else "")


def _fmt_belief(b, who=False):
    d = b.get("delta")
    arrow = "▲" if (d or 0) > 0 else "▼" if (d or 0) < 0 else "→"
    pc = b.get("prev_confidence")
    span = (f"{pc:.2f} → {b['confidence']:.2f}" if isinstance(pc, (int, float))
            else f"{b['confidence']:.2f}")
    trig = b.get("trigger") or {}
    return f"belief {_edge(b)} {span} {arrow}" + _ts(b) + (_by(trig.get("contributor")) if who else "")


def _fmt_contra(e, who=False):
    if e.get("event") == "resolve":
        return f"resolved contradiction {e.get('id', '')} → {e.get('resolution')}" + _ts(e) + \
            (_by(e.get("by")) if who else "")
    return f"opened contradiction on {_edge(e)}" + _ts(e) + \
        (_by((e.get("incoming") or {}).get("contributor")) if who else "")


def _fmt_misc(m, who=False):
    return f"misc: {str(m.get('claim', ''))[:70]}" + _ts(m) + (_by(m.get("contributor")) if who else "")


def _member_bullets(member, since):
    c, b, x, m = (_newer(_jsonl(CONTRIB), since), _newer(_jsonl(BELIEF), since),
                  _newer(_jsonl(CONTRA), since), _newer(_jsonl(MISC), since))
    out = [_fmt_contrib(r) for r in c if r.get("contributor") == member]
    out += [_fmt_belief(r) for r in b if (r.get("trigger") or {}).get("contributor") == member]
    out += [_fmt_contra(r) for r in x
            if (r.get("event") == "open" and (r.get("incoming") or {}).get("contributor") == member)
            or (r.get("event") == "resolve" and r.get("by") == member)]
    out += [_fmt_misc(r) for r in m if r.get("contributor") == member]
    active = _member_projects(member)
    return out, (f"active on {', '.join(active)}" if active else "")


def _project_bullets(value, since):
    kind, name, exp_ids = _resolve_project(value)
    ids_l = [e.lower() for e in exp_ids]
    ents = _project_entities(exp_ids)

    def src_hit(src):
        s = (src or "").lower()
        return any(e in s for e in ids_l)

    def ent_hit(r):
        return bool(ents) and (r.get("subject", "").lower() in ents or r.get("object", "").lower() in ents)

    out = [_fmt_contrib(r, who=True) for r in _newer(_jsonl(CONTRIB), since)
           if src_hit(r.get("source")) or ent_hit(r)]
    out += [_fmt_belief(r, who=True) for r in _newer(_jsonl(BELIEF), since)
            if src_hit((r.get("trigger") or {}).get("source")) or ent_hit(r)]
    out += [_fmt_contra(r, who=True) for r in _newer(_jsonl(CONTRA), since) if ent_hit(r)]
    out += [_fmt_misc(r, who=True) for r in _newer(_jsonl(MISC), since)
            if src_hit(r.get("source")) or ent_hit(r)]
    if kind == "campaign":
        status = "lineage " + " → ".join(exp_ids) if exp_ids else "campaign"
    elif kind == "hypothesis":
        status = _hyp_status(exp_ids[0])
    else:
        status = ""
    return out, status, name


def _sections(subscriber, since):
    """(header, status, bullets) per followed target, most-recent bullets last."""
    sections = []
    for kind, val in subscriptions_of(subscriber):
        if kind == "member":
            bullets, status = _member_bullets(val, since)
            header = f"member:{val}"
        else:
            bullets, status, name = _project_bullets(val, since)
            header = f"project:{name}"
        sections.append((header, status, bullets))
    return sections


# --------------------------------------------------------------------------- #
# Surfaces: a full digest, and a compact preview for the warm-start briefing.  #
# --------------------------------------------------------------------------- #
def digest(subscriber=None, mark: bool = True) -> str:
    who = _who(subscriber)
    if not subscriptions_of(subscriber):
        return ("You're not following anyone yet. follow('member:<name>') or "
                "follow('project:<H0xx|campaign>') to get a change digest here.")
    since = _seen(who)
    sections = _sections(subscriber, since)
    total = sum(len(b) for _, _, b in sections)
    out = [f"📡 Following digest — hi {who}" + (f" (since {since[:10]})" if since else "")]
    for header, status, bullets in sections:
        out.append(f"\n[{header}]" + (f"  — {status}" if status else ""))
        if bullets:
            out += [f"    • {b}" for b in bullets[-_CAP:]]
            if len(bullets) > _CAP:
                out.append(f"    … and {len(bullets) - _CAP} more")
        else:
            out.append("    (no changes since you last looked)")
    if total == 0:
        out.append("\nAll quiet across everything you follow.")
    if mark:
        _mark_seen(who, _now())
    return "\n".join(out)


def briefing_lines(subscriber=None, mark: bool = False) -> list:
    """Compact preview for the warm start: one line per followed target that has NEW changes.
    Does not advance the seen-marker by default, so the full `digest()` still shows the detail."""
    if not subscriptions_of(subscriber):
        return []
    since = _seen(_who(subscriber))
    lines = []
    for header, _status, bullets in _sections(subscriber, since):
        if bullets:
            lines.append(f"    [{header}] {len(bullets)} change(s) — e.g. {bullets[-1]}")
    if mark and lines:
        _mark_seen(_who(subscriber), _now())
    return lines


if __name__ == "__main__":
    # Hermetic demo: isolate storage, synthesize a colleague's + a project's activity, follow
    # both, and print the digest. No real logs touched.
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    MEM = tmp
    SUBS = tmp / "subscriptions.jsonl"
    SEEN = tmp / "subscription_seen.json"
    CONTRIB = tmp / "lab_contributions.jsonl"
    BELIEF = tmp / "belief_log.jsonl"
    CONTRA = tmp / "contradictions.jsonl"
    MISC = tmp / "misc_findings.jsonl"

    store_lock.append_jsonl(CONTRIB, {"ts": "2026-08-15T09:00:00", "contributor": "bob",
                                      "subject": "MYOC", "predicate": "associates", "object": "glaucoma",
                                      "source": "H002", "source_kind": "experiment", "status": "auto_merged"})
    store_lock.append_jsonl(BELIEF, {"ts": "2026-08-15T09:01:00", "subject": "MYOC",
                                     "predicate": "associates", "object": "glaucoma",
                                     "confidence": 0.83, "prev_confidence": 0.71, "delta": 0.12,
                                     "status": "supported", "trigger": {"contributor": "bob", "source": "H002"}})
    store_lock.append_jsonl(CONTRA, {"ts": "2026-08-15T09:02:00", "event": "open", "id": "k#1",
                                     "subject": "IOP", "predicate": "associates", "object": "VCDR",
                                     "incoming": {"contributor": "bob"}})

    print(subscribe("alice", "member:bob"))
    print(subscribe("alice", "project:H002"))
    print()
    print(digest("alice"))
    print("\n--- warm-start preview lines ---")
    print("\n".join(briefing_lines("alice")) or "(none)")
