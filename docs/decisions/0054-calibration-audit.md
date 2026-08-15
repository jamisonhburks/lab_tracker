# ADR-0054: Calibration audit — the substrate audits its own confidence

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
`confidence.py` (ADR-0007) is explicit that its output is "heuristic and interpretable, not a
calibrated probability." The belief lifecycle (ADR-0053) then made that number *persistent and
visible*. Visibility without accountability is a trap: a lab brain that emits confidence but
never checks it drifts toward over-confidence — exactly the failure ADR-0052 warned a
people-pleasing system would slide into. The missing Tier-2 piece is the substrate asking of
**itself**: of the edges I called 0.9, how many actually held up?

The obstacle is the usual one for calibration: there is no external labelled gold set of "true"
edges to score against.

## Options considered
1. **Skip it.** Leave confidence uncalibrated and un-audited. Cheapest, but it leaves the
   headline confidence numbers unaccountable and lets over-confidence accumulate silently.
2. **Fit a recalibration map now** (Platt/isotonic over outcomes, applied back onto the
   scorer). Tempting, but with near-zero realized outcomes today it would fit noise, and it
   couples "measure calibration" with "change the scorer" — two decisions in one PR.
3. **Diagnostic audit over the substrate's own realized signals** (chosen). Use the outcomes
   the lifecycle *already* produces as proxy labels, report reliability honestly, and stay
   humble below a data floor. Recalibration becomes a clean, separate follow-on once enough
   outcomes exist.

## Decision
Add `calibration.py` — a **read-only** audit that scores predicted confidence against realized
outcomes drawn from two independent, clearly-labelled lenses:

- **Adjudicated** — resolved contradictions. An edge believed at confidence *c* whose conflict
  resolves `upheld` → outcome 1; `overturned` → outcome 0; `contested` excluded. The strongest
  signal (a real adjudication).
- **Stability** — belief reversals. The confidence at an edge's FIRST decisive reading
  (`supported`/`refuted`) vs. whether the final reading still agrees (1) or flipped/went
  contested (0). A confident call that later reversed was over-confident given what was known.

It reports a reliability table (per-bin predicted vs. held-up rate), **ECE**, **Brier**, a net
over/under-confidence bias, and a plain-English verdict pointing at the worst-calibrated band.
Below `MIN_OUTCOMES` (8) it returns a humble "not enough settled outcomes yet" message instead
of a misleading number. Exposed as MCP shared `calibration_audit(lens)`.

## Rationale + evidence
- **Accountability is a rigor feature (ADR-0052).** The system checking its own confidence is
  the structural counter to a substrate that would otherwise only ever look more sure of
  itself. This is the honesty layer for the belief lifecycle.
- **Honest about proxies.** Outcomes are the substrate's OWN signals, not a gold standard —
  every rendering states this, and the audit refuses to report ECE below the data floor. This
  matches the codebase's standing humility ("absence of evidence ≠ evidence of absence").
- **No new epistemics, no coupling.** It only *measures*; it does not alter the scorer. The
  belief trajectory from ADR-0053 is exactly the substrate it needs, so this is a thin,
  additive read layer.
- **Verified.** The hermetic self-demo synthesizes a mildly over-confident lab (high-confidence
  calls that later reversed) and the audit correctly flags it: the 0.9–1.0 band is called ~0.94
  but only ~0.50 holds up → ECE 0.32, net bias +0.22, "POORLY CALIBRATED, over-confident,"
  worst band identified. On the real (empty) logs it returns the humble floor message.

## Consequences
- The lab can now see whether to trust its own high-confidence edges, and the research story /
  briefing gain a principled basis for down-weighting over-confident bands (a natural, small
  follow-up integration).
- Clean seam left: once realized outcomes clear the floor, an **optional recalibration map**
  (isotonic over the same outcomes) can post-process `confidence.py`'s output — a separate ADR,
  deliberately not bundled here.
- The audit is only as good as the volume of adjudications; it is honest about that and
  sharpens as more contradictions are resolved and more beliefs accumulate history.
