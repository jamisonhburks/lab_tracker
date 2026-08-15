# ADR-0056: Negative-knowledge store — remember the dead ends, check them at intake

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
The substrate remembers what worked — curated edges, confident beliefs, evaluated wins. It has
no memory of what DIDN'T. A lab that can't recall its own failures repeats them: re-running a
refuted link, re-attempting an abandoned design, re-litigating a belief that was already
overturned. The highest-leverage moment to surface a failure is at INTAKE — when someone is
about to commit to a line of work — not after they've spent the effort.

The rigor trap: not every negative is a dead end. `confidence.py` is emphatic that an
UNDERPOWERED null is not evidence of absence. A naive "graveyard" that buries every negative
result would wrongly kill live avenues and quietly suppress re-tests the lab should run.

## Options considered
1. **Nothing / rely on the research story.** The story surfaces per-hypothesis nulls after the
   fact, but there is no cross-project store and no intake check — the exact failure mode.
2. **A flat list of failed hypotheses.** Simple, but it conflates well-powered refutations with
   things merely set aside, has no provenance, and gives no intake signal.
3. **A negative-knowledge store harvested from existing signals + explicit records, queried at
   intake, with an evidenced/soft distinction** (chosen).

## Decision
Add `deadends.py` — the lab's negative knowledge, in one shape from two sources:

- **Harvested (derived on read, always in sync):** well-powered `refuted` consensus edges;
  `abandoned` hypotheses; `overturned` contradictions (ADR-0053); and failed `halt` validity
  gates (an experiment ruled INVALID — a pipeline/cohort dead end).
- **Explicit:** `record_dead_end(subject, object?, approach?, reason, why, revisit_if?)` — a human
  "we tried this and it didn't pan out," attributed and append-only.

The load-bearing distinction is **evidenced vs soft**. Evidenced dead ends (refuted, overturned,
invalid, not-reproducible, confounded) warrant "don't just repeat it." Soft ones (abandoned,
underpowered, set-aside) are flagged **revisit-worthy, not disqualifying** — carrying an optional
`revisit_if` condition. `check(subject, object?, approach?)` matches a candidate line (pair /
entity / approach, with best-effort entity normalization) and `render_check` emits a calibrated
warning: ⛔ for evidenced, ⚠ for soft, "" when clear.

Wired into **intake**: `idea.assess()` runs the check right under the verdict, so every idea
assessment says whether the line has already been tried and ruled out. Shared-tier MCP tools:
`check_dead_ends`, `record_dead_end`, `list_dead_ends`.

## Rationale + evidence
- **Intake is the point of leverage.** A dead end is only cheap if it's seen before the work
  starts; hooking `idea.assess()` puts it exactly there.
- **Honesty over a scary graveyard (ADR-0007/0052).** The evidenced/soft split encodes "absence
  of evidence ≠ evidence of absence" directly: an underpowered null nudges toward a better test,
  it doesn't forbid the avenue. This protects the lab from a store that would otherwise chill
  legitimate re-investigation.
- **Derived-on-read for the harvest.** Harvested dead ends stay consistent with the underlying
  belief/validity/hypothesis state with no sync step; only the explicit records are stored.
- **Shared, attributed.** Negative knowledge is collective — the whole lab must see it to stop
  repeating effort — so it lives in the shared tier with attribution.
- **Verified.** The hermetic demo records evidenced + soft entries and shows intake checks: an
  evidenced pair (IL6–Alzheimer's, refuted) returns ⛔ "avoid"; a soft pair (PRS–IOP, set aside)
  returns ⚠ "revisit-worthy"; an unrelated pair returns clear.

## Consequences
- Idea assessment now warns on prior dead ends; the lab has one place (`list_dead_ends`) for what
  not to repeat, and a way to log failures deliberately.
- Match quality depends on entity naming; normalization is best-effort and the check is
  deliberately inclusive (pair > entity > approach) so it errs toward surfacing a caveat.
- Clean seam: the same store pairs naturally with the coverage map (next) — dead ends mark where
  the lab has *closed* avenues; the coverage map marks where it has *unopened* ones.
