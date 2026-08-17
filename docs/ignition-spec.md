# Ignition spec — cold-starting the lab brain for a 12-person lab

**Goal.** Take the substrate from an empty scaffold to something 12 PhDs/postdocs will *keep*
using, with a **realistic day-1 experience** — no pretending the flywheel has already spun. This
is the other half of `docs/audit-kg-and-bloat.md`: the audit fixes how knowledge is *processed*;
this spec produces the *data* that makes the processing (and the whole delight layer) actually run.

Grounded in the real seams: `lab_profile.record_publication` + `profiles/<lab>.yaml`,
`briefing.briefing`, `serendipity.nudges`, `subscriptions`, `log_misc_finding` →
`group_misc_findings` → `formalize_misc_group`, `review_queue`, `graduation_candidates`,
`calibration.MIN_OUTCOMES`.

---

## The cold-start paradox (why day 1 is the whole problem)

Every feature that makes this enjoyable — warm start, serendipity, subscriptions, coverage map,
research story — reads from logs that only fill *through use*. Verified today:

- `briefing.py` bottoms out at **"(quiet since you were last here)"** → **"clear runway"** →
  "pick something fun" when a user has no history (briefing.py:99–100, 138, 167).
- `serendipity._my_entities(who)` is **empty** for anyone who hasn't contributed, so no nudges fire.
- `subscriptions` infers membership **from attribution** (subscriptions.py:9, 182) — a colleague who
  hasn't contributed yet is invisible and unfollowable.
- `calibration` needs `MIN_OUTCOMES = 8` adjudicated/reversed beliefs before it says anything.

A big lab hides this with volume — 200 sessions bootstrap it. **A 12-person lab does not.** You get
~12 people who try it *once*; if day 1 is blank, they churn before the flywheel starts. So ignition
has exactly three jobs:

1. **Seed** enough state before anyone logs in that day 1 is non-empty.
2. **Fallback** the delight features to reference-KG/profile signal so they're never blank.
3. **Fuel** the stores as a *side effect* of ordinary use, and add one weekly ritual that converges
   the group on consensus.

---

## Lever 1 · Day-0 seeding — the "lab kickoff" (one-time, ~half a day)

Manufacture the starting state. Each step maps to an existing seam, so this is mostly *running* the
code, not writing new architecture.

| # | Seed | How | Makes real on day 1 |
|---|---|---|---|
| 1 | **Roster** — all 12 members | `profiles/<lab>.yaml` `members: [...]` (today only `helmholtz-ai-health.yaml` exists) + a new `list_members()` reading the roster | `follow`, member discovery, subscriptions |
| 2 | **Prior-work profile** | Batch `record_publication` from each member's ORCID / a lab `.bib` — auto-tags onto modality×task×paradigm | **coverage map becomes a real agenda, not "all frontier fog"**; `profile_context` grounds the thinker |
| 3 | **Pre-warm the curated KG** | Run curation/deep-search on the lab's 5–10 core topics (its scope axes) once | `query_curated_kg` returns content; serendipity has KG bridges; deep-search cache has hits so nobody re-runs the same sweep |
| 4 | **Dead-ends** | A 30-min PI intake: "what have we tried that failed?" → 10–20 records | the dead-end check is useful *at intake* on day 1 (the "don't repeat failed effort" hook) |
| 5 | **A handful of held beliefs** | PI contributes 5–10 findings the lab already treats as true | warm-start "what's new"; beliefs get a trajectory; starts the road to calibration |
| 6 | **ML-method KG** | Load the existing `seeds/ml_*.json` | `recommend_methods` works day 1 |

**Highest-leverage single step is #2.** It's what turns "a generic Q&A bot" into "a thing that knows
*this lab*." The coverage map (`scope − covered`) is only meaningful once publications are tagged;
with them, a new member's very first `coverage_map` shows the lab's real open frontier.

---

## Lever 2 · Cold-start fallbacks — never show a blank (small code, big first impression)

Three targeted changes so the delight layer degrades to *lab-level* signal when *personal* signal is
absent:

- **Warm start** (`briefing.py`): when a user has no history and nothing pending, replace "clear
  runway" with profile+coverage+reference-KG content — *"The lab works on {scope}; 2 open frontier
  cells: {…}; a starter question: {…}."* The "pick something fun" branch (briefing.py:167) already
  gestures at this; make it concrete and reference-backed.
- **Serendipity** (`serendipity.py`): when `_my_entities` is empty, seed nudges from the **lab
  profile's scope entities** and reference-KG bridges near the lab's topics — so a brand-new user
  still gets one "oh, interesting" on day 1 instead of silence.
- **Coverage map**: verify it renders a prioritized agenda from the seeded profile (falls out of
  Lever 1 #2) rather than a uniform fog.

These convert "blank on day 1" → "alive on day 1," which is the entire retention battle for a small
lab.

---

## Lever 3 · One frictionless surface + a weekly ritual (so use produces fuel)

**3a · Unify the front door** (audit C3). Today `agent.py` (the REPL the README tells you to run)
has 18 tools; all collaboration/experience tools live *only* in `mcp_server.py` (51 tools) and are
unreachable from the REPL. Expose the read-only + capture tools in the daily driver:
`warm_start`, `contribute`, `log_misc_finding`, `review_queue`, `coverage_map`, `serendipity`,
`research_story`, `follow`. This is the difference between a Q&A toy and the lab's brain. **Highest
ongoing UX leverage.**

**3b · 10-second capture.** Surface `log_misc_finding` as a first-class *"jot this"* in the REPL and
in the playbook's headline flow. The fast lane already exists end-to-end (`log_misc_finding` →
`group_misc_findings` → `formalize_misc_group`, mcp_server.py:363–396) — it's just hidden behind the
7-step hypothesis ceremony. Making "capture a hunch" a one-liner is **the cheapest way to fill the
stores**, because it piggybacks on what researchers already do.

**3c · A weekly 15-minute ritual** (realistic for 12 people — this is the convergence engine):
- **Pushed digest (Mondays):** render the existing subscription/warm-start digest to a markdown/Slack
  post for the whole lab — "what reached consensus, what's pending, what's stale." Turns *pull* into
  *push* (today the digest only appears when you call a tool).
- **Graduation huddle:** walk `review_queue` + `graduation_candidates`, adjudicate `pending_review`
  and contradictions. This both moves knowledge to consensus **and** generates the adjudicated
  outcomes `calibration.py` needs — so `MIN_OUTCOMES=8` becomes reachable in ~1–2 months of weekly
  reviews instead of never.
- **Rotating "curator of the week"** among the 12 — a light social contract so the flywheel turns
  even when individuals are heads-down.

---

## A realistic timeline (set expectations honestly)

- **Day 0 (kickoff, ~½ day):** run Lever 1. Now coverage map, `query_curated_kg`, dead-end check,
  and `recommend_methods` all return real content.
- **Week 1:** each member opens it → **non-empty** warm start (from the profile), asks a few
  questions, jots a couple of hunches. Serendipity fires from seeded entities. First "a colleague is
  working on X next to me" moments.
- **Month 1:** a few dozen misc findings + contributions accrue; the first weekly huddles adjudicate
  a handful → beliefs gain trajectories, first contradictions resolved; deep-search cache has a real
  hit rate; `research_story` is usable on the first maturing project.
- **Month 2–3:** `calibration` crosses `MIN_OUTCOMES` from accumulated adjudications; the coverage
  map sharpens as pubs+findings tag more cells; the flywheel is self-sustaining.

**Be honest about calibration:** it will produce *nothing* for weeks — that's correct, not broken.
Don't promise the self-audit on day 1; promise it once the lab has settled its first ~8 disputes.

---

## What NOT to do (so ignition doesn't re-bloat)

- Don't add new epistemic/social modules until the seeded ones have real data shaping them (audit
  C1 — ~1,550 LOC is already waiting on fuel).
- Skip KG visualization for now (your call) — a seeded coverage map + a text neighborhood dump
  answers "what does the brain know?" well enough to start.
- Hold off on per-tool integrations (Zotero/Jupyter) until the core loop is sticky. The *one*
  integration worth doing early is the pushed weekly digest — it's the ritual's delivery mechanism.

---

## Minimal build list (what to actually implement, by effort)

1. **Roster + `list_members()`** reading `profiles/<lab>.yaml` — **S**. Unblocks follow/discovery day 1.
2. **Publication importer** (`.bib`/ORCID → `record_publication`) — **S/M**. Biggest "it knows us" payoff.
3. **Cold-start fallbacks** in `briefing` + `serendipity` (reference-KG/profile-backed) — **S** each.
4. **Unify the REPL surface** (collaboration + capture tools in DISPATCH) — **M**. Highest UX leverage.
5. **First-class quick-capture** (`jot`/`log_misc_finding` in REPL + playbook headline) — **S**.
6. **Kickoff runbook** (`lab-standard/kickoff.md` + a seed script: core-topic sweeps, dead-ends, beliefs) — **M**.
7. **Weekly digest push** (render existing digest to markdown; wire to the `refresh_stale`/cron schedule) — **S/M**.

**Order:** 1–3 and 5 first (all S — they make day 1 non-empty), then 4 and 6 (the surface + the
runbook), then 7. Items 1–3 + 5 are a day or two of work and single-handedly kill the cold-start
blankness that would otherwise sink adoption in a 12-person lab.
</content>
