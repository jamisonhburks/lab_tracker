# ADR-0030: MCP server — the substrate as an accessible, auditable interface

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
Reframe: the project's contribution is a **substrate, not a thinker**. A fresh Claude
session is an excellent hypothesis *generator* — what it can't do is tell grounded from
plausible, calibrate against chance, distinguish novel from rediscovered, recall the
lab's prior/negative results, or show an auditable evidence chain. All of that value was
**trapped inside `agent.py`'s tool loop**, reachable only by the local orchestrator. To be
a substrate it must be accessible and auditable from *outside* — by any thinker.

## Decision
Add **`mcp_server.py`** — a FastMCP server (local **stdio**) exposing the substrate over
the Model Context Protocol, so a fresh Claude session (Claude Desktop / Claude Code / any
MCP client) can think *with* it:
- **Tools** (queries that return EVIDENCE, not just answers): `ground_claim`, `find_paths`,
  `query_kg`, `assess_hypothesis`, `calibrate_link`, `check_novelty`,
  `query_curated_findings`, `recall_prior_work`, `propose_experiment`, and
  `recommend_methods` (activates with Stage 3 / PR #36).
- **Resources** (the audit surface): `substrate://index` plus templates
  `provenance://{id}`, `report://{id}`, `ledger://{id}`, `hypothesis://{id}`.

Two principles: (1) **no LLM inside** — the server is pure substrate; the thinker is the
external client's model, and the server only exposes what that thinker *can't* do itself
(never generation or generic web search). (2) **Privacy boundary** — tool results flow
back to the client's model, so tools emit associations / grounding / aggregates, never
row-level patient data (consistent with ADR-0001/0014).

## Rationale & evidence
- **Verified**: the server registers **9 tools + 5 resources** and a live call through the
  MCP machinery returns evidence (`ground_claim('atrial fibrillation','ischemic stroke') →
  'grounded'`). Uses the official MCP SDK via the maintained `fastmcp` framework.
- **The orchestrator is demoted to one client among many** — exactly the "substrate not
  thinker" consequence: whoever is thinking, the substrate grounds/calibrates/remembers.

## Hosting
- **Now — local stdio** (this ADR): zero infra, fully private; add to
  `claude_desktop_config.json` or `claude mcp add`. Snippets in the module docstring.
- **Later — remote HTTP** for the lab: same server code, flip the transport, host on a
  shared box beside the git-repo curated KG (storage) so every member's session connects
  to one substrate.

## Consequences
- A fresh Claude session can now draft a hypothesis → `ground_claim` → `check_novelty` →
  `recall_prior_work` → audit `provenance://` — thinking stays with the frontier model,
  grounding/memory/audit come from the substrate.
- The one unverified step (as with the anthropic adapter) is a real client connecting over
  stdio — the last mile the user wires up.
