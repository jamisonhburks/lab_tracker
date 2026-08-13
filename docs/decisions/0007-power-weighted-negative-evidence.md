# ADR-0007: Power-weighted negative evidence

- **Date:** 2026-08-12
- **Status:** Accepted

## Context
Confidence must incorporate negative/refuting results — but not all negatives are
equal. A null from an underpowered or flawed study is weak evidence of absence.

## Options considered
- Flat subtraction (`support − refute`), counting each negative as −1.
- **Power/quality-weighted** negatives, with a distinct status for
  under-investigated links.

## Decision
Weight each refuting study by its **informativeness ≈ statistical power /
methodology quality**, and emit a status that distinguishes a genuine null from a
poorly-tested one — including **`promising_but_poorly_tested`** with a re-test flag.

## Rationale & evidence
- **Absence of evidence ≠ evidence of absence.** Bayesian: an underpowered null
  has likelihood ratio ≈ 1 (`P(null|effect) ≈ P(null|no effect)`), so it must
  barely move belief.
- A link that only *looks* negative because it was poorly powered becomes a
  **re-test candidate** (a cheap win hiding under bad prior studies) — arguably the
  highest-value output a hypothesis agent produces.
- File-drawer bias means the few published negatives are themselves a biased
  sample — reinforcing "don't over-weight them."

## Consequences
- `kg_schema.Evidence` gained `direction / power / sample_size / ci / risk_of_bias`;
  `confidence.score_association` aggregates support/refute/investigation with
  power-weighting. The synthesizer (ADR-0011) extracts these fields from abstracts.
