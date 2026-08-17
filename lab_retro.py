"""lab_retro — a lab-workflow RETROSPECTIVE: how is the lab actually working?

The substrate captures rich per-member process telemetry (run ledgers, dead ends, coverage gaps,
calibration outcomes, promotion state, attributed contributions) but never STEPS BACK to ask the
meta-question: across everyone, what is the lab doing well, where is it losing time, and what are
the cheap wins? This module is that step back — a coach, not a scoreboard.

It COMPOSES existing signals (LLM-free, read-only) into three lists:
  - WORKING          — process that's paying off; keep it and propagate it.
  - NEEDS ATTENTION  — where effort is being wasted (seeds burned on a design that won't pass,
                       runs killed by validity gates, dead ends re-hit, mis-calibration).
  - OPTIMIZE         — cheap wins available now (adoptable methods unused, findings ready to
                       promote, duplicated effort to coordinate, reviews waiting).

Design principle — COACHING, NOT SURVEILLANCE. The lab view (member=None) AGGREGATES and
de-identifies the "needs attention" items: it names hypotheses (shared WIP) and counts, never
grades a person. Positive items may credit people. For pointed, per-person feedback, pass
`member=<name>` — that view is meant to be read BY that person, privately. There is deliberately
no ranking of members: a tool that grades colleagues chills the honest logging the whole
substrate depends on.

Signals are the substrate's OWN, LLM-free. The thinker (Claude, via the `lab_retro` MCP tool)
reads the report and narrates the WORKING / NOT-WORKING / OPTIMIZE story — that's the
substrate/thinker split (ADR-0030). Everything here degrades gracefully: a missing module or an
empty log drops its signal, never crashes the retro.
"""

import json
import os
from pathlib import Path

MEM = Path(__file__).parent / "memory"
CONTRIB = MEM / "lab_contributions.jsonl"
MISC = MEM / "misc_findings.jsonl"
SESSIONS = MEM / "sessions"
REPORTS = Path(__file__).parent / "reports"

# thresholds — deliberately conservative so the retro flags real patterns, not noise
_BURN_MIN_RUNS = 5          # this many runs with zero passes = the design, not the seed, is wrong
_MISCAL_BIAS = 0.10         # |net bias| above this (with enough outcomes) = a real calibration lean


def _jsonl(p: Path) -> list:
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()] if p.exists() else []


def _members() -> list:
    try:
        import subscriptions
        return subscriptions.known_members()
    except Exception:
        return []


def _dead_end_key(de) -> str:
    parts = [str(getattr(de, "subject", "") or "").lower().strip(),
             str(getattr(de, "object", "") or "").lower().strip(),
             str(getattr(de, "approach", "") or "").lower().strip()]
    return "|".join(parts)


# --------------------------------------------------------------------------- #
# Signal extraction — LLM-free, each source guarded so one failure isn't fatal. #
# --------------------------------------------------------------------------- #
def signals(member: str = None) -> dict:
    """The raw computed signals behind the retro (structured, testable). `member` filters to one
    researcher's attributed work where a signal is attributable; lab-level signals (calibration,
    coverage aggregate) are labelled as such."""
    sig = {"member": member, "members": _members(),
           "hypotheses": [], "dead_ends": {"total": 0, "evidenced": 0, "repeated": []},
           "calibration": {"n": 0, "ece": 0.0, "net_bias": 0.0, "meaningful": False,
                           "scope": "lab", "leaning_members": 0},
           "coverage": {"adoptable": 0, "frontier": 0, "examples": []},
           "promotion": {"cleared_not_promoted": [], "session_candidates": 0, "pending_review": 0},
           "overlap": [], "participation": {"active_members": 0, "total_members": len(_members())}}

    # --- run ledgers: per active hypothesis, is it progressing, stalled, burning, or invalid? ---
    try:
        import worklog
        for s in worklog.active_hypotheses(statuses=("approved", "running", "complete")):
            hid = s["id"]
            rs = worklog.runs(hid)
            by = sorted({r.get("by") for r in rs if r.get("by")})
            if member and member not in by:
                continue                              # member view: only hypotheses they've run
            minr = s.get("min_runs")
            n, npass, ninv = s["n_runs"], s["n_pass"], s["n_invalid"]
            status = s.get("status")
            sig["hypotheses"].append({
                "id": hid, "title": s.get("title", ""), "status": status,
                "n_runs": n, "min_runs": minr, "n_pass": npass, "n_invalid": ninv, "members": by,
                "burning": n >= _BURN_MIN_RUNS and npass == 0 and status in ("approved", "running"),
                "stalled": n == 0 and status in ("approved", "running"),
                "cleared": npass >= (minr or 1) and status not in ("complete", "abandoned"),
                "has_invalid": ninv > 0,
            })
    except Exception:
        pass

    # --- dead ends: how many, and is the lab RE-HITTING the same wall? ---
    try:
        import deadends
        des = deadends.all_dead_ends()
        if member:
            des = [d for d in des if getattr(d, "contributor", None) == member]
        groups = {}
        for d in des:
            groups.setdefault(_dead_end_key(d), []).append(d)
        repeated = []
        for key, ds in groups.items():
            sources = {getattr(d, "source", None) or getattr(d, "contributor", None) for d in ds}
            if len(ds) >= 2 and len(sources) >= 2:    # same line, ≥2 distinct origins = a re-do
                label = ds[0].subject + (f" → {ds[0].object}" if ds[0].object else "") \
                    + (f" [{ds[0].approach}]" if ds[0].approach else "")
                repeated.append((label, len(ds)))
        sig["dead_ends"] = {"total": len(des),
                            "evidenced": sum(1 for d in des if getattr(d, "strength", "") == "evidenced"),
                            "repeated": sorted(repeated, key=lambda x: -x[1])}
    except Exception:
        pass

    # --- calibration: is confidence honest? Per-MEMBER when a member is asked for, else lab-level
    #     with a de-identified count of members whose OWN history shows a lean. ---
    try:
        import calibration
        if member:
            a = calibration.audit_member(member)
            sig["calibration"] = {"n": a["n"], "ece": a["ece"], "net_bias": a["net_bias"],
                                  "meaningful": a["meaningful"], "scope": member, "leaning_members": 0}
        else:
            a = calibration.audit("all")
            per = calibration.audit_by_member("all")
            leaning = sum(1 for m in per.values()
                          if m["meaningful"] and abs(m["net_bias"]) >= _MISCAL_BIAS)
            sig["calibration"] = {"n": a["n"], "ece": a["ece"], "net_bias": a["net_bias"],
                                  "meaningful": a["n"] >= calibration.MIN_OUTCOMES,
                                  "scope": "lab", "leaning_members": leaning}
    except Exception:
        pass

    # --- coverage: gaps that a KNOWN method already solves (adoptable = cheap win) ---
    try:
        import coverage
        cov = coverage.compute(member=member or None)
        adopt = cov.get("adoptable", [])
        sig["coverage"] = {"adoptable": len(adopt), "frontier": len(cov.get("frontier", [])),
                           "examples": [f"{m}×{t}" for (m, t, *_ ) in adopt[:3]]}
    except Exception:
        pass

    # --- promotion state: good work stuck below the tier it's earned ---
    try:
        for h in sig["hypotheses"]:
            report = REPORTS / f"{h['id']}_evaluation.md"
            if h["cleared"] and not report.exists():
                sig["promotion"]["cleared_not_promoted"].append(h["id"])
        contribs = _jsonl(CONTRIB)
        sig["promotion"]["pending_review"] = sum(1 for c in contribs
                                                 if c.get("status") == "pending_review"
                                                 and (not member or c.get("contributor") == member))
        cand = 0
        if SESSIONS.exists():
            import session_journal
            for d in SESSIONS.iterdir():
                if not d.is_dir():
                    continue
                try:
                    pr = session_journal.SessionJournal(session_id=d.name, root=SESSIONS).promotion_review()
                    if "ready to consider for SHARED WIP" in pr:
                        cand += 1
                except Exception:
                    continue
        sig["promotion"]["session_candidates"] = cand
    except Exception:
        pass

    # --- duplicated effort: entities worked by ≥2 members unaware ---
    try:
        rows = _jsonl(CONTRIB) + _jsonl(MISC)
        ent_to_who = {}
        for r in rows:
            who = r.get("contributor")
            for k in ("subject", "object"):
                e = str(r.get(k) or "").strip()
                if e:
                    ent_to_who.setdefault(e.lower(), (e, set()))[1].add(who)
        overlap = [(label, sorted(w for w in who if w))
                   for (label, who) in ent_to_who.values() if len({x for x in who if x}) >= 2]
        if member:
            overlap = [(lbl, ws) for (lbl, ws) in overlap if member in ws]
        sig["overlap"] = sorted(overlap, key=lambda x: -len(x[1]))[:5]
    except Exception:
        pass

    # --- participation: how much of the lab is actually in motion ---
    try:
        active = set()
        import worklog
        for s in worklog.active_hypotheses(statuses=("approved", "running", "complete")):
            active |= {r.get("by") for r in worklog.runs(s["id"]) if r.get("by")}
        active |= {c.get("contributor") for c in _jsonl(CONTRIB) if c.get("contributor")}
        sig["participation"] = {"active_members": len({a for a in active if a}),
                                "total_members": len(sig["members"])}
    except Exception:
        pass

    return sig


# --------------------------------------------------------------------------- #
# Buckets — turn raw signals into the three coaching lists.                    #
# --------------------------------------------------------------------------- #
def _buckets(sig: dict, member: str = None):
    working, attention, optimize = [], [], []

    # WORKING
    for h in sig["hypotheses"]:
        if h["cleared"]:
            bar = f"{h['n_pass']}/{h['min_runs']}" if h["min_runs"] else f"{h['n_pass']}"
            working.append(f"{h['id']} cleared its pre-registered bar ({bar} passing runs) — "
                           "the min_runs discipline is doing its job.")
    cal = sig["calibration"]
    _cal_who = "Your calls are" if cal.get("scope") not in (None, "lab") else "The lab is"
    _cal_whose = "your own" if cal.get("scope") not in (None, "lab") else "adjudicated"
    if cal["meaningful"] and abs(cal["net_bias"]) < _MISCAL_BIAS and cal["ece"] < 0.15:
        subj = "Your calibration is honest" if cal.get("scope") not in (None, "lab") \
            else "Calibration is honest"
        working.append(f"{subj} — net bias {cal['net_bias']:+.2f}, ECE {cal['ece']:.2f} "
                       f"over {cal['n']} {_cal_whose} outcomes. The confidence means something.")
    part = sig["participation"]
    if part["total_members"] and part["active_members"]:
        working.append(f"{part['active_members']} of {part['total_members']} members are actively "
                       "logging runs / contributing — the process is live, not shelfware.")

    # NEEDS ATTENTION  (lab view: hypothesis IDs + counts only, no naming of people)
    for h in sig["hypotheses"]:
        if h["burning"]:
            attention.append(f"Burning seeds — {h['id']} has {h['n_runs']} runs and 0 passes. That's "
                             "a DESIGN problem, not a seed problem; change the approach, not the RNG.")
        if h["has_invalid"]:
            attention.append(f"{h['id']}: {h['n_invalid']} run(s) invalidated by a HALT validity gate "
                             "— a pipeline/cohort defect to fix before more runs, not a real null.")
        if h["stalled"]:
            attention.append(f"Stalled — {h['id']} is {h['status']} but has 0 runs logged. Either "
                             "start it or move it to abandoned so it stops looking active.")
    for label, n in sig["dead_ends"]["repeated"]:
        attention.append(f"Repeated dead end — “{label}” recorded {n}× from different origins. "
                         "check_dead_ends at intake would have caught the re-do.")
    if cal["meaningful"] and cal["net_bias"] >= _MISCAL_BIAS:
        attention.append(f"{_cal_who} systematically OVER-confident (net bias {cal['net_bias']:+.2f} "
                         f"over {cal['n']} {_cal_whose} outcomes) — gate promotions harder, trust nulls more.")
    elif cal["meaningful"] and cal["net_bias"] <= -_MISCAL_BIAS:
        attention.append(f"{_cal_who} systematically UNDER-confident (net bias {cal['net_bias']:+.2f} "
                         f"over {cal['n']} {_cal_whose} outcomes) — findings that actually held are being discarded.")

    # OPTIMIZE
    cov = sig["coverage"]
    if cov["adoptable"]:
        eg = f" (e.g. {', '.join(cov['examples'])})" if cov["examples"] else ""
        optimize.append(f"{cov['adoptable']} modality×task gap(s) already have an ADOPTABLE method in "
                        f"the KG{eg} — you don't need to invent one; go adopt it (coverage_map).")
    prom = sig["promotion"]
    if prom["cleared_not_promoted"]:
        optimize.append(f"{len(prom['cleared_not_promoted'])} finding(s) cleared the bar but aren't "
                        f"written up/promoted ({', '.join(prom['cleared_not_promoted'])}) — "
                        "reports/ + contribute() before the context goes cold.")
    if prom["session_candidates"]:
        optimize.append(f"{prom['session_candidates']} session(s) have components ready to promote "
                        "from personal notes to shared WIP (promotion_review).")
    if sig["overlap"]:
        egs = ", ".join(lbl for lbl, _ in sig["overlap"][:3])
        optimize.append(f"{len(sig['overlap'])} entit(y/ies) are being worked by ≥2 members "
                        f"unaware ({egs}) — a 5-minute sync avoids duplicated effort.")
    if prom["pending_review"]:
        optimize.append(f"{prom['pending_review']} contribution(s) waiting in the review queue "
                        "(review_queue) — unblock a colleague.")
    if cal.get("scope") == "lab" and cal.get("leaning_members"):
        n = cal["leaning_members"]
        optimize.append(f"{n} member(s) show a calibration lean in their OWN history — nudge them to "
                        "their private lab_retro(member=\"…\") view (not named here by design).")

    return working, attention, optimize


# --------------------------------------------------------------------------- #
# Rendering.                                                                   #
# --------------------------------------------------------------------------- #
def render(member: str = None) -> str:
    """The coaching report: WORKING / NEEDS ATTENTION / OPTIMIZE. `member=None` → the lab view
    (attention items aggregated, de-identified). `member=<name>` → that person's private view."""
    sig = signals(member)
    working, attention, optimize = _buckets(sig, member)

    if member:
        head = [f"🔬 Lab retro — private coaching for {member}",
                "   Your own working record; not shared or ranked. Read it, act on it."]
    else:
        head = ["🔬 Lab retro — the lab's workflow, coached as a whole",
                "   Coaching the process, not grading people: attention items are aggregated. "
                "Run lab_retro(member=\"<you>\") for your own private view."]

    def _sec(title, items, empty):
        if not items:
            return [f"\n{title}", f"    {empty}"]
        return [f"\n{title}"] + [f"    • {i}" for i in items]

    out = head
    out += _sec("✅ WORKING — keep doing this", working,
                "(no standout wins yet — log runs and promote cleared findings to build the record.)")
    out += _sec("⚠️  NEEDS ATTENTION — where the lab is losing time", attention,
                "(nothing flagged — no burned seeds, invalidated runs, re-hit dead ends, or mis-calibration.)")
    out += _sec("🚀 OPTIMIZE — cheap wins available now", optimize,
                "(no low-hanging fruit detected right now.)")
    return "\n".join(out)


def retro_lines(member: str = None, max_lines: int = 3) -> list:
    """A compact preview for the warm start: the single most important item from each bucket."""
    sig = signals(member)
    working, attention, optimize = _buckets(sig, member)
    lines = []
    if attention:
        lines.append(f"⚠️  {attention[0]}")
    if optimize:
        lines.append(f"🚀 {optimize[0]}")
    if working and len(lines) < max_lines:
        lines.append(f"✅ {working[0]}")
    return lines[:max_lines]


if __name__ == "__main__":       # tiny self-demo over whatever the local substrate holds
    print(render())
