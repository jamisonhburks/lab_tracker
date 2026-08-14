# ADR-0024: Pre-registered validity gates (interim, hypothesis-orthogonal)

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The experiment loop had no interim check that an experiment was *working*: the runner
only checked artifacts exist, and the evaluator ran once at the end against the
hypothesis. The natural fix — "evaluate interim results against prior knowledge and
update the plan" — carries a serious trap: letting hypothesis-relevant interim results
reshape a running analysis is **p-hacking**, and it breaks the pre-registration /
separation-of-concerns discipline that makes results (like H002's honest null) credible.

## Decision
Add **`validity.py`** — pre-registered, **hypothesis-ORTHOGONAL** interim gates that
verify the *machinery*, never the hypothesis-relevant result:
- `cohort_integrity` — both arms present, each ≥ min (catches empty/mislabeled arms)
- `data_scale` — values finite and on the expected (log) scale
- `negative_control` — genes with no expected effect stay null (validates FDR control)
- `positive_control` — a gene with a robust, hypothesis-INDEPENDENT effect behaves as known

Gates are declared in the spec/config `validity_gates:` block (pre-registration) and run
interim. A **`halt`** gate that fails raises `ValidityError` — the experiment stops and
is marked **invalid** (a bug), *not* "negative". A **`flag`** gate records a warning that
surfaces in the evaluation and the provenance card. Because gates are orthogonal to the
tested hypothesis, they catch bugs **without** enabling interim steering.

Adaptivity that *is* driven by results stays out of the running experiment: it belongs to
the campaign/program layer (ADR-0025), where a failed gate or a verdict spawns the *next*
atomic experiment rather than mutating the current one.

## Rationale & evidence
- **Verified on H001** (synthetic): all three gates run and pass — `cohort_integrity`
  (100/100), `data_scale` (max 8.34 ≤ 30), `negative_control` (null-gene fraction
  significant = 0.011, confirming FDR control). Written to `experiments/H001/validity.json`
  and surfaced in the provenance card.
- **Catches the real bug**: a `cohort_integrity` gate on `{AD: 0, control: 140}` — exactly
  the H002 `AD='AA'` coding bug that produced 0 cases — **halts** the run with a clear
  message, instead of the downstream crash it caused before. H002 is now gated on both
  cohorts + data scale (pre-registered).
- **It caught a real issue on its first real-data run**: on H002 the `data_scale` gate
  flagged GSE48350's expression max of **59.24** — anomalous for clean log2 microarray
  data (log2 RMA tops out ~16), a scale question the original H002 analysis never
  surfaced (its evaluator had only *noted* "confirm each series is log-scaled"). Kept as a
  `flag` (the 30-cutoff is uncertain for this series) rather than a halt — the honest
  response is to surface it for follow-up, not tune the threshold until it passes.
- **Orthogonality is the safeguard**: gates check controls / integrity, never the T2D–AD
  panel results — so they can run interim without touching what's being tested.

## Consequences
- Experiments fail fast and *legibly* on machinery bugs, distinct from honest negatives.
- Validity results are a tracked per-experiment artifact (`validity.json`) folded into the
  provenance view.
- The "check against prior knowledge / update the plan" intuition is satisfied safely:
  orthogonal gates here (halt/flag), plan changes at the campaign layer (ADR-0025).
