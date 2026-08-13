# ADR-0002: Layered memory with claim-level provenance

- **Date:** 2026-08-11
- **Status:** Accepted

## Context
A research agent needs to accumulate and recall knowledge, and — critically —
must not launder a guess into a "known fact." Hallucinated citations are worse
than no answer in a clinical context.

## Options considered
- A single chat transcript / vector store.
- **Cognitively-typed layers**: working (the message list), episodic (what
  happened), semantic (what's true), later ontological (typed relations).

## Decision
Build **layered memory** (working / episodic / semantic) where every stored
finding binds **each claim to its own sources** (not a pooled bag), and a
**seen-source guardrail** filters stored provenance to what was actually retrieved.

## Rationale & evidence
- Claim→sources binding (chosen over a separate `sources` list) keeps a statement
  and its evidence from drifting apart.
- The guardrail: after the model proposes sources, drop any it didn't genuinely
  retrieve this run — so provenance is always real. This is the core
  anti-hallucination mechanism, reused later by the KG layer and the curator.
- Consolidation (episodic → semantic) mirrors biological memory.

## Consequences
- Provenance flows through every later layer (KG grounding, confidence, curator).
- "Read = tool, write = code": the model chooses what to recall; code decides what
  to persist — it can't forget to save or fake what it saved.
