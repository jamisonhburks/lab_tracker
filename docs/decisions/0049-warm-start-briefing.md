# ADR-0049: Warm-start briefing (the enjoyable front door)

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
Everything so far optimized the substrate's *rigor and memory*. Nothing optimized whether it's a
*pleasure to work with* — and research is emotionally hard (lonely, slow-feedback, mostly dead
ends). The first experience lever to pull: **momentum and re-entry.** Opening a session should
feel like a thoughtful colleague catching you up, not a blank prompt — especially because the
substrate already remembers everything needed to do that.

## Decision
Add **`briefing.py`** — a READ-ONLY composition (no new store) that greets a researcher with a
personal, four-part warm start:

1. **Where you left off** — from your most recent session journal (mode + last note).
2. **What's new in the lab since you were last here** — new consensus edges, and contributions
   touching *your* entities (inferred from your own contributions/misc), as a real **delta**
   against a per-user `briefing_seen.json` timestamp.
3. **Waiting on you** — the review queue, promotion candidates in your notes, stale search topics.
4. **One suggested next step** — a single prioritized nudge (review pending → promote ready →
   formalize an ad-hoc session → check a colleague's overlap → refresh stale → "pick something fun").

Wired into the agent REPL (printed at startup, before the new journal is created, so "where you
left off" reads the *previous* session) and the MCP personal tier as `warm_start`.

## Rationale & evidence
- **Pure composition of what we built.** It reads the session journal, `lab_contributions`,
  `misc_findings`, and the deep-search cache — no new persistence except a tiny per-user "last
  seen" marker. The delta is what makes "what's new" feel alive rather than a static dump.
- **Momentum + recognition, cheaply.** Re-entry is zero-friction (you see your thread), your work
  comes back to you ("touching your entities", consensus wins), and there's always one concrete
  thing to do — the opposite of a cold blank prompt.
- **Calibrated tone.** Warm, concise, a little personality (☕/✓/↔/→), and deliberately **no
  leaderboard** — recognition is about connection and impact, not scores (which distort a lab).
- **Fast + graceful.** No network; every section degrades to silence if its store is absent, so a
  fresh install still greets cleanly ("clear runway").
- **Verified**: full briefing renders the four sections from seeded data; the "what's new" delta
  correctly goes **quiet** on the second open (after `briefing_seen` is marked); the suggested step
  respects priority (pending review first). Personal MCP tier = **8 tools** (＋`warm_start`); all
  modules import clean; `memory/` gitignored so the seen-marker stays local.

## Consequences
- The first "make it enjoyable" feature ships — a daily-feel upgrade that turns session open from
  a blank page into a colleague's rundown.
- Natural next enjoyment features compose on the same signals: serendipity nudges (surface the
  surprising overlaps this already computes), the personal research-story narrative, and
  preference/persona memory to tune tone + defaults per researcher.
