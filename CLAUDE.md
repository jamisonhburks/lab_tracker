# CLAUDE.md — lab_tracker substrate

This repo is a **lab research substrate**, not an ordinary codebase. It holds what the lab knows
(curated knowledge graph + findings), what's in flight (hypotheses, experiments, campaigns), and the
tools to query and contribute to both. Think *with* it, and leave your work where the next session —
and the shared lab — can pick it up.

## Start every session here
1. **Call `warm_start` first** (an MCP tool). It briefs you on active work, recent findings, and
   what's yours vs the lab's — so you resume instead of restarting. If you don't see the substrate
   tools, the MCP servers aren't connected yet → see [`QUICKSTART.md`](QUICKSTART.md).
2. **If the human says "onboard me"** (or is new): follow
   [`lab-standard/onboarding.md`](lab-standard/onboarding.md) — call `onboarding_status`, then
   `add_member`, and ask **one short question at a time**. Never send a wall of questions.
3. **Before scaffolding, organizing, or conforming a project**, read [`AGENTS.md`](AGENTS.md) — it
   routes by intent to the right playbook. Don't scaffold from memory.

## Two substrates are wired for you (see `.mcp.json`)
- **`lab-shared`** — the lab's consensus KG + contribution log (shared tier; the only writer runs on
  the cluster). Query it freely; contribute **deliberately** per
  [`lab-standard/promotion.md`](lab-standard/promotion.md).
- **`my-personal`** — your private tier (episodic memory + session journal). Never shared.

Attribution is automatic (your cluster identity / the lab proxy), so just do the work. Knowledge
moves WIP → consensus by a deliberate act, never silently.
