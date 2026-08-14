# ADR-0031: Three-tier substrate scoping (personal / shared-WIP / shared-consensus)

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The substrate reframe (ADR-0030) needed the tiering made real. The key distinction is
**conclusion vs process**, not personal vs shared: a session's unfinished *thinking* is
personal, but the research *process* (experiments, method choices, tests, validity gates)
is worth tracking centrally **even before a conclusion** — so the group can see what's
in-flight and not duplicate it. Only the *concluded* consensus knowledge needs the gate.

## Decision
Add **`SUBSTRATE_SCOPE`** (`personal | shared | all`, default `all`) to `mcp_server.py`,
so one instance serves a chosen tier and you run separate deployments:

- **PERSONAL** (local, private): `recall_prior_work` (episodic) + `search_notes` (personal
  semantic — in-progress distillations). Never crosses to shared except via `contribute()`.
- **SHARED — WIP ("group semantics")**: `list_active_work` (every tracked hypothesis/
  experiment/campaign with STATUS + validity-gate counts) and the audit resources
  (`provenance://`, `report://`, `ledger://`, `hypothesis://`, `substrate://index`).
  Provisional, un-gated — visibly "in progress".
- **SHARED — CONSENSUS**: `query_curated_findings` (critic-gated, confidence-scored) plus
  the KG query/calibration/novelty tools. What the lab *believes*.

Deploy a **shared** instance (hosted for the lab, over the git-repo KG) and a **personal**
instance (local, over your episodic+semantic). Same code; scope + hosting differ.

## Rationale & evidence
- **Verified**: `all` → 12 tools, `shared` → 10 (no personal), `personal` → 2 (only your
  episodic+semantic). `list_active_work` surfaces `H001 [approved] evaluated · gates 3/3`,
  `H002 [approved] evaluated · gates 2/3`, `campaign t2d-ad-shared-genes: H001 → H002` —
  process + status, mid-flight, un-gated.
- **Why WIP is shared but ungated**: it's *process*, self-evidently provisional; the value
  is coordination (don't repeat in-flight work) and transparency. Only *interpretations*
  (findings) need the critic gate — those are the consensus tier.
- **Personal semantic stays personal**: `search_notes` reads your local store and imports
  the embedder lazily, so the shared deployment needs no LLM/embedder and no private data
  ever enters the shared surface.

## Consequences
- The three tiers are explicit and enforced by scope, not convention.
- Sets up the two remaining pieces cleanly: the **consensus** tier is where the
  git-repo `contribute()` write-path lands; the **shared** deployment is where the remote
  HTTP transport goes (hosted beside the git-repo KG).
