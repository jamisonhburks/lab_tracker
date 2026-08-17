# ADMIN.md — set up the lab substrate (before anyone joins)

Yes — before members join you do two things, in order: **(A) host the one shared substrate**, then
**(B) register yourself as the first user** (exactly like a member). You wear two hats; they're
separate. Full reference: [`docs/deployment.md`](docs/deployment.md).

## A. Host the shared substrate (once)

The shared tier is **one service — the only writer** — on a cluster node. Members never run it;
they point at it.

1. **Place the shared repo** on the node, on a persistent/shared path. This is the SHARED copy,
   distinct from members' personal clones (they each clone their own).
2. **Install deps** there: `./setup.sh` (creates `.venv` with `requirements.txt` incl. `fastmcp`).
3. **Run the service** as a long-lived job (systemd unit or SLURM — see deployment.md §1):
   ```sh
   MCP_TRANSPORT=http MCP_HOST=0.0.0.0 MCP_PORT=8443 \
   SUBSTRATE_SCOPE=shared KG_BACKEND=combined \
   .venv/bin/python mcp_server.py
   ```
   `combined` = Hetionet + Monarch harmonized; the reference KG loads once at startup (minutes;
   size the node's RAM).
4. **Front it with TLS + auth** (caddy/nginx, deployment.md §2). After the proxy authenticates a
   user it must inject the identity header the substrate reads:
   `header_up X-Substrate-Contributor {verified-user}`. Never let a client set that header on an
   unauthenticated path — the proxy owns it. This is what attributes shared contributions to the
   real person.
5. **Mint a `LAB_SUBSTRATE_TOKEN`** per person (including yourself).
6. **Publish the shared client config.** The repo ships with the **solo** `.mcp.json` by default, so
   switch it to the shared template and point it at your node:
   `cp examples/mcp.shared.json .mcp.json`, set `lab-shared.url` (e.g. `https://your-node:8443/mcp`),
   then commit & push. Members' clones then inherit the shared config. (Members can still run solo by
   copying `examples/mcp.solo.json` back over it.)
7. **Smoke-check the host** (deployment.md "Quick check"): Uvicorn is up; `GET /mcp` in a plain
   browser returns 406 (expected — MCP needs proper headers).

## B. Register yourself as the first user (once)

Now you do exactly what a member does ([`QUICKSTART.md`](QUICKSTART.md)) — plus you seed the roster:

1. Clone the repo into your **own** working dir (not the shared copy); `./setup.sh`;
   `export LAB_SUBSTRATE_TOKEN=<yours>`.
2. `code .` → approve both MCP servers (`lab-shared`, `my-personal`).
3. Say **"onboard me."** The intake calls `add_member(<you>)` — which adds you to the roster in
   `profiles/<lab>.yaml` `members:` — and seeds your profile. Your personal tier lives in your own
   clone.
4. **Verify attribution end-to-end:** run `warm_start`, then contribute one finding and confirm the
   contribution log shows it under **your** name (proves the proxy header path works).

## C. Hand off to members

Give each person the **repo URL + their `LAB_SUBSTRATE_TOKEN`**, and point them at `QUICKSTART.md`.
They self-register on "onboard me" (`add_member` is idempotent), so you don't pre-create accounts.
If you'd rather seed the roster up front, edit `profiles/<lab>.yaml` `members:` or call `add_member`
for each — either way it converges.

## D. During the alpha — track tickets

Members' sessions file bug/rough-edge reports with the `file_ticket` MCP tool (CLAUDE.md tells them
to). They land in the **shared** tracker (`memory/tickets.jsonl` on your node — the cron snapshot in
§5/deployment.md versions it). Triage from a session or the shell:

```sh
python tickets.py list          # or: list open | ack | closed   (blocker→low, oldest first)
python tickets.py ack   T-0007
python tickets.py close T-0007 "fixed in <commit>"
python tickets.py stats
```

From a Claude session the same is `list_tickets` / `update_ticket`. Tickets are attributed to the
reporter automatically (the proxy's `X-Substrate-Contributor`), so you can see who hit what.

**Auto-filed tickets:** any *unhandled* tool error also files a ticket on its own (marked `[auto]`,
severity `high`), so silent crashes surface even when the session doesn't mention them. These are
**deduplicated** while open — a recurring error bumps an `(xN)` occurrence count instead of spamming
new tickets. So a burst of `[auto] … (x40)` means one bug hit forty times, not forty bugs.

---

## Minimal shared node for a trusted alpha (no TLS, one command)

If standing up TLS + SLURM (§A) is too much for a first test but you still want collaborators to
**share one brain** — and their tickets/work to land **centrally with you** instead of siloed on
each laptop — run the minimal node. (The default per-clone config is *solo*, so without this every
collaborator is an isolated brain and you never see their feedback.)

**You (once), on a node your collaborators can reach, from a clone on SHARED filesystem:**
```sh
./run_shared.sh                       # → http://<this-node>:8765/mcp   (scope=shared)
# or: MCP_PORT=9000 KG_BACKEND=hetionet ./run_shared.sh
```
Shared FS matters: `register_project` records a path, and the node globs it — so the node must be
able to read collaborators' project dirs (same cluster / Lustre).

**Each collaborator (once):** switch from the solo default to the shared-dev config and put in the
node URL + their own name:
```sh
cp examples/mcp.shared-dev.json .mcp.json
# then edit .mcp.json:  url → http://<your-node>:8765/mcp   and   X-Substrate-Contributor → their name
```
Their Claude Code now talks to your one shared substrate: `register_project`, `contribute_finding`,
`file_ticket`, `list_active_work`, `list_members` all read/write the **same** brain, attributed to
whoever the header names.

**Collect the alpha feedback:** tickets now land on your node — `python tickets.py list` (or
`list_tickets` in a session) shows everyone's, attributed. `my_work` / `warm_start` work across the
shared substrate.

⚠ **Trust model:** no TLS and no auth — attribution trusts each client's `X-Substrate-Contributor`
header (a client can claim any name). Fine for a trusted internal alpha on a private network. Before
it's a real multi-writer lab, move to §A (a reverse proxy that **owns** the header after auth) and
`examples/mcp.shared.json`.
