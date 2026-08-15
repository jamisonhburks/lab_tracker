"""briefing — the warm start: a colleague's rundown when you open a session.

Composes existing substrate signals into a friendly, personal briefing — where you left off,
what changed in the lab since you were last here, what's waiting on you, and one suggested next
step. READ-ONLY: it's the pleasant front door, not a new store. Personalized by contributor + a
per-user 'last seen' timestamp, so "what's new" is a real delta. Kept FAST (no network).
"""
import json
import os
from datetime import datetime
from pathlib import Path

MEM = Path(__file__).parent / "memory"
SEEN = MEM / "briefing_seen.json"
CONTRIB = MEM / "lab_contributions.jsonl"
MISC = MEM / "misc_findings.jsonl"
SESSIONS = MEM / "sessions"


def _who(contributor):
    return contributor or os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "you"


def _jsonl(p):
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()] if p.exists() else []


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


def _latest_session():
    if not SESSIONS.exists():
        return None
    dirs = [d for d in SESSIONS.iterdir() if d.is_dir()]
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


def _edge(c):
    return f"{c.get('subject','?')} —{c.get('predicate','?')}→ {c.get('object','?')}"


def briefing(contributor=None, mark: bool = True) -> str:
    who = _who(contributor)
    now = datetime.now().isoformat(timespec="seconds")
    since = _seen(who)
    contribs, misc = _jsonl(CONTRIB), _jsonl(MISC)
    my_ents = {r[k].lower() for r in contribs + misc if r.get("contributor") == who
               for k in ("subject", "object") if r.get(k)}

    out = [f"☕ Warm start — hi {who}."]

    # 1) where you left off (personal)
    left = None
    sess = _latest_session()
    if sess:
        try:
            import session_journal
            j = session_journal.SessionJournal(session_id=sess.name, root=SESSIONS)
            notes = [l for l in j._read().splitlines() if l.strip() and not l.startswith("#")]
            mode = j.session_mode()
            tail = notes[-1][:130] if notes else "(no notes)"
            out.append(f"\n• Where you left off — {sess.name} [{mode}]: {tail}")
            left = mode
        except Exception:
            pass

    # 2) what's new in the lab since you were last here (shared)
    def _newer(rows):
        return [r for r in rows if not since or r.get("ts", "") > since]
    new_consensus = [c for c in _newer(contribs) if c.get("status") == "auto_merged"]
    touch_mine = [c for c in _newer(contribs) if c.get("contributor") != who
                  and (c.get("subject", "").lower() in my_ents or c.get("object", "").lower() in my_ents)]
    out.append("\n• What's new in the lab" + (f" since {since[:10]}" if since else "") + ":")
    if new_consensus:
        out.append(f"    ✓ {len(new_consensus)} finding(s) reached consensus — e.g. "
                   + "; ".join(_edge(c) for c in new_consensus[:2]))
    if touch_mine:
        c = touch_mine[0]
        out.append(f"    ↔ {len(touch_mine)} touching your entities — e.g. {_edge(c)} "
                   f"(by {c.get('contributor', '?')})")
    if not (new_consensus or touch_mine):
        out.append("    (quiet since you were last here)")

    # 2b) what's new on people/projects you follow (subscriptions; preview, doesn't mark seen)
    follow = []
    try:
        import subscriptions
        follow = subscriptions.briefing_lines(contributor, mark=False)
    except Exception:
        pass
    if follow:
        out.append("\n• What's new on people/projects you follow:")
        out += follow

    # 3) waiting on you (fast: no network)
    pending = [c for c in contribs if c.get("status") == "pending_review"]
    stale_n = 0
    try:
        import deep_search
        stale_n = len(deep_search.stale_topics())
    except Exception:
        pass
    promo = None
    if sess:
        try:
            import session_journal
            pr = session_journal.SessionJournal(session_id=sess.name, root=SESSIONS).promotion_review()
            if "ready to consider for SHARED WIP" in pr:
                promo = pr
        except Exception:
            pass
    waiting = []
    if pending:
        waiting.append(f"{len(pending)} contribution(s) in the review queue")
    if promo:
        waiting.append("components in your notes ready to promote to shared WIP")
    if stale_n:
        waiting.append(f"{stale_n} stale search topic(s) to refresh")
    out.append("\n• Waiting on you:")
    out += [f"    • {w}" for w in waiting] or ["    • nothing pending — clear runway."]

    # 3b) serendipity — surprising, relevant connections (cheap nudges only; no KG/network)
    nudges = []
    try:
        import serendipity
        nudges = serendipity.nudges(who, max_nudges=2, deep=False, mark=True)
    except Exception:
        pass
    if nudges:
        out.append("\n✨ Serendipity:")
        out += [f"    {n}" for n in nudges]

    # 4) one suggested next step
    if pending:
        step = f"review the {len(pending)} pending contribution(s) — review_queue()."
    elif promo:
        step = "promote your ready components to shared WIP (see promotion_review)."
    elif left == "adhoc_series":
        step = "formalize your ad-hoc session (formalize_retroactively) — or log it as misc."
    elif touch_mine:
        step = f"take a look — a colleague just added {_edge(touch_mine[0])} on one of your entities."
    elif follow:
        step = "open your following digest (subscription_digest) — updates on people/projects you track."
    elif stale_n:
        step = "refresh a stale search topic (stale_topics / refresh_stale.py)."
    elif nudges:
        step = "chase a ✨ serendipity nudge above — those connections found you."
    else:
        step = "pick something fun — assess_idea on a new angle, or browse group_misc_findings for a latent theme."
    out.append(f"\n→ Suggested next: {step}")

    if mark:
        _mark_seen(who, now)
    return "\n".join(out)
