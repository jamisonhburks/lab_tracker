# QUICKSTART — join the lab substrate (clone → open in VS Code → "onboard me")

You use **Claude in VS Code** (already signed in). There's **no Ollama and no API key** — Claude is
the model; this repo gives your Claude session the lab's tools and memory over MCP.

## Fastest path — try onboarding solo (no shared node, no token)

```sh
git clone <repo-url> lab_tracker && cd lab_tracker
./setup.sh
cp examples/mcp.solo.json .mcp.json      # one local server, all tiers — see examples/README.md
code .                                   # approve the "lab" server when Claude Code prompts
```
Then in the Claude Code chat say **“onboard me.”** That's the whole solo test — one local substrate,
everything (KG, onboarding, tickets) works offline. To join a real shared lab later, use
`examples/mcp.shared.json` (below).

---

## One-time setup (each member)

Run this from wherever you keep your work — your own directory / home on the cluster (the path is up
to you; the steps are the same anywhere):

```sh
cd <your-working-dir>               # your personal dir on the cluster (wherever that is)
git clone <repo-url> lab_tracker && cd lab_tracker
./setup.sh                          # creates .venv and installs deps (incl. fastmcp)
echo 'export LAB_SUBSTRATE_TOKEN=<your-token>' >> ~/.bashrc && source ~/.bashrc
code .                              # open THIS folder in VS Code
```

`code .` opens the repo root, so Claude Code auto-loads [`CLAUDE.md`](CLAUDE.md) and `.mcp.json`.
When Claude Code prompts, **approve the two MCP servers**:

- **lab-shared** — the lab's shared knowledge (read + contribute deliberately).
- **my-personal** — your private memory + journal (runs locally from your clone; never shared).

That's the whole setup. You do **not** run the shared server — you just point at it (the URL is in
`.mcp.json`; your token authorizes you).

## Every session

In the Claude Code chat, the first time say **"onboard me"** — a ~2-minute, skippable intake. After
that, just start working: Claude calls `warm_start` to brief itself and picks up where you and the
lab left off. Onboarding is resumable — say "onboard me" again anytime to finish.

## Troubleshooting

- **No substrate tools / "warm_start not found":** the MCP servers didn't connect. Check
  `LAB_SUBSTRATE_TOKEN` is set, that `./setup.sh` finished, and re-approve the servers in Claude
  Code.
- **Different Python setup (conda/modules):** you don't edit `.mcp.json`. The launcher
  (`mcp_personal.sh`) auto-detects the interpreter — repo `.venv`, then `$VIRTUAL_ENV`, then
  `python3`. To force a specific one, `export SUBSTRATE_PYTHON=/path/to/python`. Just make sure
  `requirements.txt` (incl. `fastmcp`) is installed into whatever it uses.

## For the lab admin (once, before anyone joins)

Host the one shared substrate, then register yourself as the first user. Ordered runbook:
[`ADMIN.md`](ADMIN.md) (which references [`docs/deployment.md`](docs/deployment.md) for the host
details). After that, hand each member the repo URL + a `LAB_SUBSTRATE_TOKEN`.
