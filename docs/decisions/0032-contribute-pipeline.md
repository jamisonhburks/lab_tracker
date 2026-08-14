# ADR-0032: The `contribute()` write-path into shared consensus

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The substrate was fully *readable/auditable* (MCP, ADR-0030/0031) but not *writable* — a
thinker could ground and audit, but findings couldn't flow back into the one gated tier
(shared consensus). This is the capstone of the multi-user design: the critic-gated,
attributed contribution pipeline.

## Decision
Add **`contribute.py`**. A finding is: (1) **normalized** to canonical entities;
(2) **critic-gated** — literature findings re-read the cited abstract; experiment findings
are verified by their **committed provenance** (not an abstract); (3) **routed
conservatively**:
- **rejected** — critic caught junk / unsupported,
- **auto_merged** — corroborates an already-`supported` edge (same direction) + critic
  accepts → merged into the consensus curated KG; evidence + confidence update
  (multi-user aggregation),
- **pending_review** — NOVEL or CONTRADICTORY / status-shifting → held for peer review;
and (4) **appended to the shared contributions log with attribution** (`SUBSTRATE_CONTRIBUTOR`).
`review_queue()` lists what's pending. Exposed as MCP shared-tier tools
(`contribute_finding`, `review_queue`).

Git deployment mapping: the append **is a PR**, the critic **is CI**, review **is PR
approval**, merge **is accept**; aggregation is the confidence projection over the log.

## Rationale & evidence
- **Verified** all three routes (contributor `jamison`): a novel experiment finding
  (verified by H002 provenance) → `pending_review`; a junk entity (`GSE12345`) → `rejected`;
  corroborating an already-`supported` edge → `auto_merged` (confidence updated). The
  review queue shows the pending item with attribution.
- **Multi-user aggregation for free**: `kg_writer` already merges evidence for the same
  triple and `confidence` re-scores — so more independent contributors → sharper,
  power-weighted confidence, with disagreement surfaced as `contested` rather than
  overwritten.

## Bug fix surfaced by this build
`contribute` calls `normalize_entity` as the *first* KG op, which exposed a latent
cold-start bug: `_norm_index` set `_NORM = {}` and then called `_meta()`, whose graph load
runs `_reset()` and clobbered `_NORM` back to `None` mid-build. Fixed to load first, build
into a local, assign at the end (matching `_meta`/`_index`). It never bit before because
other tools always loaded the KG first.

## Consequences
- The read→write loop is closed: a thinker can ground/audit *and* contribute back, under a
  conservative gate.
- The shared-consensus tier is now writable under peer review; the local log
  (`memory/lab_contributions.jsonl`) is gitignored — the git-repo store is the deployment.
- Remaining: the actual remote git-repo + HTTP-transport deployment (infra, not code).
