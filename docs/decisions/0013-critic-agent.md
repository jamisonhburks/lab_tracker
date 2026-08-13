# ADR-0013: Critic agent + test-driven evaluation

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
The synthesizer's extraction is noisy (junk entities like `CID11879209`, off-topic
or source-unsupported associations). We wanted an adversarial filter — the second
specialist from ADR-0011 — and, first, a way to *evaluate* it.

## Options considered
- A plausibility-only LLM filter.
- A KG-membership filter (reject anything not in the KG) — **rejected**: it would
  violate closed-world humility (ADR-0008) and kill novel discoveries.
- **Source-faithful, type-aware adversarial critic**, grounding-informed but not
  grounding-vetoed.

## Decision
`critic.criticize(record)` judges four axes — **well_formed / source_supported
(re-reads the cited abstract) / type_valid / plausible** — and returns
accept | reject | uncertain + reason. **Novelty is never a reason to reject.**
Exposed as the `criticize_curated_kg` tool; verdicts persist on each record for audit.

## Evaluation (test-driven — `eval_critic.py`)
Battery: gold spot-check (P/R/F1), **fabrication injection** (source-unsupported
claims → must reject), **novelty-preservation control** (valid novel links → must
NOT reject), type-violation injection, downstream grounding ablation, consistency.
The two headline metrics are **in tension**: fabrication/junk/type **recall** and
**novelty preservation** — a good critic scores high on both.

## Rationale & evidence
- Source-faithfulness catches the real failure mode (extraction attributing a claim
  to a paper that doesn't support it) — and correctly rejects even *true-but-
  unsupported* claims (bad provenance is still wrong).
- The novelty-preservation control is the distinctive test: it guards the
  novel ≠ false stance that a naïve KG filter would break.
- **Verified** on the 6-case seed: accuracy 1.00, fabrication/junk/type recall
  1.00, novelty preserved 1.00. Small set — indicative, not definitive.

## Consequences
- Cleans curator output before it hardens into the KG.

## Update (2026-08-13) — hardening
- Gold set expanded 6 → 12. It **caught a real gap**: the 14B critic accepted a
  dataset accession (`GSE12345`) as an entity (accuracy 0.92) — exactly what a
  bigger gold set is for.
- Fix: a **deterministic accession pre-filter** (rules for GSE/GDS/SRR/phs/CID… →
  auto-reject, no LLM) in front of the LLM judgment — a stronger rule+LLM hybrid.
  Seed set → **1.00** (accuracy / fabrication-recall / novelty-preservation).
- Added **adversarial multi-vote** (`votes=N`, majority) and a **consistency** test
  (1.00 agreement on repeated runs).
- Remaining: downstream-ablation test; grow the gold set with real curator output.
