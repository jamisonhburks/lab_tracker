# ADR-0059: Lab-workflow retrospective — a coach over the substrate's own process signals

- **Date:** 2026-08-16
- **Status:** Accepted

## Context
The substrate captures rich, attributed PROCESS telemetry per member — run ledgers (`worklog`),
negative knowledge (`deadends`), coverage gaps (`coverage`/`lab_profile`), the belief lifecycle +
calibration (`beliefs`/`calibration`), promotion state (`session_journal`, `contribute`), and
attributed contributions (the lab logs). But nothing ever STEPS BACK across everyone to ask the
meta-question a good PI or chief-of-staff asks: *how is the lab actually working — what's paying
off, where is time being lost, and what are the cheap wins?* Each signal exists in isolation; no
unit reads them together at the lab grain.

This is also the capability the founder identified as the product's core daily value (a lab
workflow coach), distinct from the one-shot research agents (Elicit/Edison/Benchling): those help
you do a task; this observes and improves how a lab does research over time.

Two risks shaped the design:
1. **Surveillance.** "Analyze how everyone is working" is one step from a manager's ranking
   dashboard — which would chill the honest logging the whole substrate depends on.
2. **Scope creep / new epistemics.** The temptation to invent new scores rather than compose the
   substrate's existing, already-trusted signals.

## Options considered
1. **A per-member scoreboard / ranking.** Rejected: it grades people, inverts the incentive to log
   honestly, and violates the substrate's trust model.
2. **A new metrics store with bespoke productivity scores.** Rejected: duplicates existing signals
   and introduces un-audited epistemics (ADR-0052's rigor concern).
3. **A read-only composition layer over existing signals, framed as coaching** (chosen): LLM-free
   roll-up → three coaching lists, with the thinker narrating on top (the substrate/thinker split,
   ADR-0030).

## Decision
Add `lab_retro.py` — a read-only retrospective that composes existing signals into **WORKING /
NEEDS ATTENTION / OPTIMIZE**:

- **WORKING** — cleared-bar findings (the `min_runs` discipline paying off), honest calibration,
  active participation.
- **NEEDS ATTENTION** — seeds burned on a design that won't pass (many runs, zero passes),
  runs killed by HALT validity gates, stalled hypotheses, re-hit dead ends (same line from ≥2
  origins), and calibration bias.
- **OPTIMIZE** — ADOPTABLE method gaps unused, findings ready to promote, duplicated effort to
  coordinate, reviews waiting.

**Coaching, not surveillance — enforced in code, not just docs.** The lab view (`member=None`)
AGGREGATES and de-identifies the attention items: it names hypotheses (shared WIP) and counts,
never a person; a test asserts the run author never appears in the lab view. Pointed feedback
requires `member=<name>` and is framed as that person's OWN private view. There is deliberately no
ranking of members.

**Per-member calibration attribution.** `calibration` now tags each realized `Outcome` with the
member whose confident call it scores — the stability lens via the first decisive revision's
`trigger.contributor`, the adjudicated lens via `_edge_owner()` (the established belief's most
recent decisive contributor, recovered from belief-event history, since the contradiction ledger
stores no owner). New `audit_member()` / `audit_by_member()` compute per-member ECE/Brier/net-bias,
staying humble below `MIN_OUTCOMES` so no one is graded on two data points. The lab view surfaces
only a de-identified count of members with a lean; the member view names their own.

Surfaces: the `lab_retro` MCP tool (shared tier) and a compact preview hook in the warm-start
briefing (top item per bucket).

## Consequences
- The lab's process telemetry becomes legible as a single coached picture without any new store or
  new epistemics — pure composition, degrades gracefully when a source is missing.
- The coaching-not-surveillance framing is a load-bearing design constraint the beta depends on;
  future signals must respect the aggregate-in-lab-view / name-only-in-own-view rule.
- The `Outcome.who` attribution is a reusable seam: per-member calibration can later feed
  differential promotion gating, not just the retro.
- Calibration attribution is only as good as `trigger.contributor` coverage on belief events;
  unattributed outcomes stay in the lab-level audit but drop out of the per-member map (honest).
