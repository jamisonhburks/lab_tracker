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

## Your substrate tools come over MCP (see `.mcp.json`)
- **Solo (default):** one local `lab` server serves everything — the shared KG/findings **and** your
  personal tier — with no shared node or token. This is what a fresh clone gives you.
- **Shared lab:** two servers — **`lab-shared`** (the lab's consensus KG + contribution log; the only
  writer runs on the cluster) and **`my-personal`** (your private tier — episodic memory + journal,
  never shared).

Either way: query freely; contribute to the shared tier **deliberately** per
[`lab-standard/promotion.md`](lab-standard/promotion.md). Attribution is automatic (your identity /
the lab proxy), so just do the work. Knowledge moves WIP → consensus by a deliberate act, never silently.

## Alpha mode — file tickets when things break
This is an **alpha**. When something errors, is confusing, behaves wrong, or a tool is missing,
**call `file_ticket`** (one per issue) — title + what happened, steps, expected vs actual, and any
error/ids in `context`; set `severity` (low|medium|high|blocker) and an `area` tag. It goes to the
admin's tracker; you're attributed automatically. Don't just work around a bug silently — a
ten-second ticket is how the alpha improves. (Admin triages with `list_tickets` / `tickets.py`.)
