# ADR-0045: Remote/HTTP MCP deployment (one shared substrate on the cluster)

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
Everything through ADR-0044 ran the MCP substrate over **stdio** — a local subprocess, one user.
The whole point of the substrate, though, is a *shared* lab brain. Given the lab's actual setup
(one repo on a shared-filesystem cluster), we need one substrate service that every member's
Claude session reaches over the network, contributes to, and sees the same in-flight work in —
without each person re-loading the multi-GB reference KG or corrupting the append-only logs.

## Decision
Add an **HTTP transport mode** and the three things a shared deployment needs, all env-gated so
the local stdio default is unchanged:

- **Transport switch** — `MCP_TRANSPORT=http` (with `MCP_HOST`/`MCP_PORT`) runs FastMCP's
  streamable-HTTP transport (uvicorn); default stays `stdio`. One instance on a cluster node
  loads the reference KG **once** and serves the whole lab.
- **Per-request attribution** — `_caller()` reads `X-Substrate-Contributor` (or
  `X-Forwarded-User`) from the HTTP request (set by a reverse proxy *after* auth) and threads it
  into `contribute()` / `log_misc()` via a new `contributor=` param, so writes are attributed to
  the real person, not the server's process user. Over stdio it returns None → env fallback
  (`SUBSTRATE_CONTRIBUTOR`/`$USER`), unchanged for single-user.
- **Write serialization** — `store_lock` (POSIX `flock` on a sidecar `.lock`) wraps the two
  append-only logs (`contribute`, `log_misc`) and the curated-KG **read-modify-write**
  (`kg_writer.add_association`), so parallel contributions from many members (one async server,
  or a stray local writer) can't interleave or clobber.
- **`docs/deployment.md`** — systemd/container recipe, reverse-proxy TLS+auth with the
  attribution header, per-user client config (shared HTTP + local personal), git snapshot/review
  role, and the privacy invariant.

## Rationale & evidence
- **Env-gated, nothing breaks.** `python mcp_server.py` is still stdio; `python agent.py`
  unaffected. The shared mode is opt-in and additive — the three-tier scoping (ADR-0031) and the
  no-LLM-in-the-server design (ADR-0030) already did the hard part.
- **The shared FS makes it clean.** One writer + advisory file locks = safe concurrent consensus
  on the same repo; the KG loads once (huge RAM/time win); WIP artifacts are just files everyone
  reads. Personal tiers stay local (per-user stdio) — private thinking never hits the shared node.
- **Attribution is proxy-owned, not client-trusted.** The header is set after authentication by
  the reverse proxy; clients must not set it on an unauthenticated path.
- **Privacy preserved.** It's the lab's own cluster behind TLS; the substrate emits associations/
  grounding/aggregates, never row-level data (unchanged invariant).
- **Verified**: locked append (3/3 lines), `_caller()` returns None off-HTTP, `contribute(...,
  contributor="alice")` attributes correctly, stdio remains the default, and
  `MCP_TRANSPORT=http` boots (uvicorn up; `/mcp` correctly 406s a plain GET). `fcntl` locking is
  no-op-safe where unavailable.

## Consequences
- The lab can now run one substrate the whole group shares — the step from "works on my machine"
  to "the lab shares one brain." `related-work.md`'s "show the union beats the twins" evaluation
  becomes runnable across real users.
- `fastmcp>=3.0` (pulls uvicorn) is required only for the HTTP server; stdio needs nothing new.
- Follow-ups: built-in bearer-token auth (vs. a proxy), and a git-mediated review flow for the
  consensus tier (PRs as the gate) if a lab prefers async audit over the shared-FS real-time path.
