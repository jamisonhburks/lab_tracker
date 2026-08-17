# QUICKSTART — join the lab substrate (clone → open in VS Code → "onboard me")

You use **Claude in VS Code** (already signed in). There's **no Ollama and no API key** — Claude is
the model; this repo gives your Claude session the lab's tools and memory over MCP.

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
  Code. `my-personal` needs `.venv/bin/python` to exist (that's what `setup.sh` creates).
- **Different Python setup (conda/modules):** edit `.mcp.json` → `my-personal.command` to your
  interpreter, and install `requirements.txt` + `fastmcp` into it.

## For the lab admin (once, not per member)

Stand up the **one** shared service on a cluster node and put its URL in `.mcp.json`
(`lab-shared.url`), then issue each member a `LAB_SUBSTRATE_TOKEN`. See
[`docs/deployment.md`](docs/deployment.md): `MCP_TRANSPORT=http SUBSTRATE_SCOPE=shared
KG_BACKEND=combined`, behind a TLS reverse proxy that injects `X-Substrate-Contributor` from each
authenticated user (that's what makes shared contributions attribute to the real person).
