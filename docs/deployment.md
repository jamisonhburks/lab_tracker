# Deployment — one shared substrate for the lab (HTTP on your cluster)

Local, per-user use needs nothing: `python agent.py`, or a personal stdio MCP server. This doc
is for the **shared** deployment — one substrate service on your cluster that every lab member's
Claude session queries and contributes to, over the same lab repo on a shared filesystem.

## Architecture

```
   cluster node (lab repo on shared FS, big RAM)
   ┌───────────────────────────────────────────────┐
   │ ONE shared MCP service — the only writer        │
   │ SUBSTRATE_SCOPE=shared  KG_BACKEND=combined     │
   │ MCP_TRANSPORT=http  →  https://lab-node:8443/mcp │
   │ · reference KG loaded ONCE, served to everyone  │
   │ · reads/writes memory/*.jsonl + hypotheses/ …   │
   │ · writes serialized via store_lock (flock)      │
   │ · per-request attribution (X-Substrate-Contributor) │
   └───────────────────────────────────────────────┘
        ▲ https             ▲                ▲
   Alice's Claude      Bob's Claude     Carol's Claude   (each: lab-shared URL
        │                   │                │            + a LOCAL personal stdio server)
```

- **Shared tier** (one service): consensus KG, contribution log, misc pool, WIP artifacts,
  reference KGs. One writer ⇒ safe concurrent contributions.
- **Personal tier** (per user, local): episodic + semantic + session journal. Never shared —
  each member runs their own `SUBSTRATE_SCOPE=personal` stdio server locally.

## 1. Run the shared service

Env: `MCP_TRANSPORT=http` `MCP_HOST=0.0.0.0` `MCP_PORT=8443` `SUBSTRATE_SCOPE=shared`
`KG_BACKEND=combined` (and `SUBSTRATE_CONTRIBUTOR` only as a fallback — real attribution comes
per-request, below).

**systemd unit** (`/etc/systemd/system/lab-substrate.service`):
```ini
[Service]
WorkingDirectory=/srv/lab/lab_tracker
Environment=MCP_TRANSPORT=http MCP_HOST=0.0.0.0 MCP_PORT=8443
Environment=SUBSTRATE_SCOPE=shared KG_BACKEND=combined
ExecStart=/srv/lab/venv/bin/python mcp_server.py
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
`fastmcp>=3.0` must be installed (it pulls uvicorn). The reference KG loads once at startup
(~minutes on `combined`); size the node's RAM accordingly. As a long SLURM job instead, run the
same `ExecStart` on a dedicated node and publish its host:port.

## 2. TLS + auth (reverse proxy) and per-user identity

Put a reverse proxy (caddy/nginx) in front for TLS and authentication. **After** the proxy
authenticates the user, it injects the identity header the substrate reads:

```
# caddy sketch — authenticate, then set the attribution header from the verified user
reverse_proxy /mcp* localhost:8443 {
    header_up X-Substrate-Contributor {http.auth.user.id}
}
```

`mcp_server._caller()` reads `X-Substrate-Contributor` (or `X-Forwarded-User`) per request, so
`contribute_finding` / `log_misc_finding` attribute to the **real person**, not the server's
process user. Never let clients set that header directly on an unauthenticated path — the proxy
must own it.

## 3. Client config (each lab member)

Claude Desktop `claude_desktop_config.json` — the shared HTTP substrate + a local personal server:
```jsonc
{"mcpServers": {
  "lab-shared":  {"url": "https://lab-node:8443/mcp",
                  "headers": {"Authorization": "Bearer <your-lab-token>"}},
  "my-personal": {"command": "python",
                  "args": ["/ABS/PATH/mcp_server.py"],
                  "env": {"SUBSTRATE_SCOPE": "personal"}}}}
```
(The token is what your proxy verifies to set `X-Substrate-Contributor`.)

## 4. Concurrency

`store_lock` (POSIX `flock` on a sidecar `.lock`) serializes the append-only logs and the
curated-KG read-modify-write, so parallel contributions can't interleave or clobber. **Run one
shared writer.** If a member also runs `agent.py` locally against the *same* shared files, the
lock still protects them, but keeping the shared service the sole writer is cleanest.

## 4b. Scheduled cache refresh (cron)

The deep-search cache ages (ADR-0047/0047). A weekly job re-distils stale topics so the primary KG
stays current without waiting for someone to re-ask. It runs the **local model** (curate_literature
distils), so run it on a host with the model (or `LLM_BACKEND=anthropic`), not necessarily the
shared HTTP node:
```cron
0 3 * * 0  cd /srv/lab/lab_tracker && /srv/lab/venv/bin/python refresh_stale.py --max 20
```
`refresh_stale.py --dry-run` lists what's stale; the MCP `stale_topics` tool surfaces the same to
any session.

## 5. Git's role (audit + the consensus gate)

On a shared FS you don't need git for real-time sharing, but use it as the audit + review layer:
- **WIP + auto-merged corroborations** land on the shared FS in real time → a cron `git commit`
  snapshots `memory/` + `hypotheses/` + `experiments/` for versioning / blame / rollback.
- **The gated consensus tier** (`review_queue`, novel/contradictory) is where a human approves —
  optionally materialized as GitHub PRs/issues before a finding merges into the curated KG.

## 6. Privacy

It's *your* cluster — data never leaves the institutional environment, preserving the local-first
guarantee. Keep it on the internal network behind TLS + auth. The invariant holds regardless of
transport: the substrate emits **associations / grounding / aggregates, never row-level patient
data**. `data/raw/` stays read-only and off the wire.

## Quick check

```sh
MCP_TRANSPORT=http MCP_PORT=8443 SUBSTRATE_SCOPE=shared KG_BACKEND=combined python mcp_server.py
# → "Uvicorn running on http://0.0.0.0:8443"; GET /mcp returns 406 to a plain browser (expected —
#   MCP needs the proper Accept/session headers). Point a client at https://lab-node:8443/mcp.
```
