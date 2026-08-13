# ADR-0004: Hetionet as interim KG; backend-swappable; OptimusKG deferred

- **Date:** 2026-08-12 (OptimusKG retried 2026-08-13, still locked)
- **Status:** Accepted

## Context
The ontological layer needs a real, heterogeneous biomedical KG. First choice was
**OptimusKG** (Zitnik Lab, Biolink-native, 190k nodes / 21.8M edges) — the ideal
target and aligned with our schema direction.

## Options considered
- **OptimusKG** — best fit, but its Harvard Dataverse dataset (DOI
  10.7910/DVN/IYNGEV) returns **HTTP 202 (locked)** for days, likely a **2.0
  reingest** (repo issues reference "release 2.0"). No mirror.
- **Hetionet v1.0** — 47k nodes / 2.25M edges, CC0, downloadable now, the
  canonical Rephetio graph.
- Monarch KG (Biolink, larger), PrimeKG (also Dataverse).

## Decision
Use **Hetionet now**, behind a **backend-swappable interface** (`KG_BACKEND` =
demo | hetionet | optimuskg). OptimusKG is a one-call swap when Dataverse unlocks.

## Rationale & evidence
- Hetionet is small (loads fully in-memory), CC0 (no governance friction), and is
  the exact graph our path-scoring/DWPC math is based on (Rephetio, eLife 2017).
- Backend-swappable means nothing depends on OptimusKG being available now.
- The lit review (ADR-0005) established that *KG quality dominates model size*, so
  a real curated KG matters more than which one.

## Consequences
- The demo pair (AF↔stroke) isn't in Hetionet's 137 curated diseases; examples use
  Crohn's ↔ ulcerative colitis instead.
- Retune column names / align to Biolink when OptimusKG (or its 2.0) lands.
