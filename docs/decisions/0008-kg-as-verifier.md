# ADR-0008: KG-as-verifier grounding check (novel ≠ false)

- **Date:** 2026-08-12
- **Status:** Accepted

## Context
The LLM proposes hypotheses in prose; we wanted a training-free way to regularize
hallucinations by checking claims against the KG (cf. KG-CoI).

## Options considered
- Binary "KG supports it / doesn't" — but that would falsely reject novel
  hypotheses (the KG is incomplete: closed-world).
- **Graded, humble grounding**: does the reasoning traverse a *majority-trustworthy
  short subgraph path*?

## Decision
`check_connection` grades each claimed link:
`grounded | weakly_grounded | novel_unverified | off_graph`. Crucially,
**KG absence ≠ false** — `novel_unverified`/`off_graph` are flagged for
*verification*, never rejected.

## Rationale & evidence
- Closed-world humility (same principle as ADR-0007): the KG can't confirm a
  genuinely novel hypothesis, so absence must not count against it.
- Trust matters, not just connectivity: a path via low-trust edges (mere
  co-occurrence, text-mined) is `weakly_grounded`; a short path via curated
  sources is `grounded`.
- This is the hybrid's hallucination regularizer, and no training is needed.

## Consequences
- Grounding tags persist to episodic memory and later fold into the confidence
  score (ADR: PR #13) — grounded claims get a prior boost, novel ones are never
  penalized.
