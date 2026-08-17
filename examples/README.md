# MCP config templates

Claude Code reads `.mcp.json` at the repo root. Copy the one you want over it:

## Solo / alpha test (default for one person, zero config)
```sh
cp examples/mcp.solo.json .mcp.json
```
One local server serving **all** tiers (KG + onboarding + tickets). No shared node, no token —
just open the repo in VS Code, approve the `lab` server, and say **“onboard me.”**

## Shared lab (multi-member)
```sh
cp examples/mcp.shared.json .mcp.json
```
Then set `lab-shared.url` to your hosted node and `export LAB_SUBSTRATE_TOKEN=…`. Two servers:
`lab-shared` (the one consensus substrate) + `my-personal` (your private tier). See
[`../ADMIN.md`](../ADMIN.md) and [`../docs/deployment.md`](../docs/deployment.md).

The repo ships with the shared template active as `.mcp.json`; for a **first solo run, copy the solo
one over it** (it stays a local, uncommitted change).
