# MCP config templates

Claude Code reads `.mcp.json` at the repo root. **The repo ships with the solo config active**, so a
fresh clone works standalone with no edits. These templates let you switch:

## Solo / alpha test — the shipped default (`.mcp.json` already matches this)
[`mcp.solo.json`](mcp.solo.json): one local `lab` server serving **all** tiers (KG + onboarding +
tickets). No shared node, no token — open the repo in VS Code, approve the `lab` server, and say
**“onboard me.”** (Only needed if you previously switched away: `cp examples/mcp.solo.json .mcp.json`.)

## Shared — one login node, no daemon (simplest)
```sh
cp examples/mcp.shared-fs.json .mcp.json
```
When everyone works from the **same login node**. Point `lab-shared.args` at ONE shared clone's
`mcp_personal.sh` (absolute path); it writes the shared tier there, attributed by `$USER`.
`my-personal` stays in your own clone. No running service — same-node file locks keep writes safe.
See [`../ADMIN.md`](../ADMIN.md) → "Shared directory on ONE login node".

## Shared — trusted internal alpha, HTTP node (across nodes / remote)
```sh
cp examples/mcp.shared-dev.json .mcp.json
```
For the one-command shared node (`../run_shared.sh`). Edit `lab-shared.url` → your node
(`http://<node>:8765/mcp`) and `X-Substrate-Contributor` → your name. No token/TLS — attribution
trusts the header. Everyone shares one brain; tickets/work land centrally. See
[`../ADMIN.md`](../ADMIN.md) → "Minimal shared node for a trusted alpha".

## Shared — production (hosted, TLS + auth)
```sh
cp examples/mcp.shared.json .mcp.json
```
Then set `lab-shared.url` to your hosted node and `export LAB_SUBSTRATE_TOKEN=…`. Two servers:
`lab-shared` (the one consensus substrate) + `my-personal` (your private tier). A reverse proxy
owns the `X-Substrate-Contributor` header after auth. See [`../ADMIN.md`](../ADMIN.md) and
[`../docs/deployment.md`](../docs/deployment.md).
