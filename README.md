# lab-tracker

A shared **research substrate** for a lab — a "lab brain" that remembers what the lab knows (a
curated knowledge graph + layered memory), tracks what's in flight (hypotheses, experiments,
campaigns), and lets every member query and contribute to both. You work with it through **Claude
in VS Code** (the Claude Code extension); the substrate is exposed as MCP tools. Every claim carries
its provenance and a confidence grounded in the evidence.

## What it is

Knowledge moves through three tiers:

- **Personal** — your episodic memory + session journal. Private, per member.
- **Shared WIP** — hypotheses / experiments / campaigns in flight, visible to the lab
  (`list_active_work`). Un-gated "here's what I'm doing."
- **Shared consensus** — reviewed findings promoted into the curated knowledge graph
  (`query_curated_findings`). Gated "this is established."

Members use ~70 MCP tools (all under one `lab` server) to:

- **Orient** — `warm_start` (where things stand + what's waiting on you), `my_work` (your unfinished
  work across the tiers, with the next step), `list_members`, `coverage_map` (where the lab's coverage thins).
- **Query knowledge** — `query_kg`, `find_paths` (A→B→C mechanism discovery), `query_curated_findings`,
  `check_novelty`, `check_dead_ends`.
- **Do research** — `preregistration`, `propose_experiment`, `assess_hypothesis`, `recommend_methods`,
  `log_run`, `record_dead_end`.
- **Bring existing work in** — conform a project to the lab layout (**non-destructive**: it never
  edits or deletes your files — only relocates, reversibly), then `register_project` so the lab can
  see it; `record_publication`.
- **Contribute** — `contribute_finding` → `review_queue` → `graduate` moves a defensible result into
  shared consensus.
- **Feedback (alpha)** — `file_ticket` reports bugs / rough edges to the admin's tracker
  (unhandled crashes auto-file themselves).

Findings are bound to their sources; KG grounding + power-weighted evidence feed a calibrated
confidence, and absence of support is treated as *novel / unverified*, never *false*.

## Get started (each member)

You use **Claude in VS Code** (already signed in). No API keys to manage — Claude is the model.

```sh
git clone <repo-url> lab_tracker && cd lab_tracker
./setup.sh          # creates .venv and installs deps
code .              # open this folder in VS Code
```

Claude Code detects the config on open and asks you to **approve the `lab` MCP server** — approve it,
then say **“onboard me”** in the chat (a ~2-minute, skippable, resumable intake). Full walkthrough:
**[`QUICKSTART.md`](QUICKSTART.md)**.

Day to day: **“warm start”** to resume where you and the lab left off; **“what’s my unfinished
work?”** for what’s pending with the next step; **“conform `<path>` to the lab standard”** to bring
an existing project in.

## Run the shared brain (admin)

By default each clone is a private, solo substrate. To give the lab **one shared brain** — so members
see each other’s WIP and feedback lands centrally — run the shared node:

```sh
./run_shared.sh     # one HTTP node, SUBSTRATE_SCOPE=shared (trusted internal alpha, no TLS)
```

Members then switch from the solo default to `examples/mcp.shared-dev.json` pointed at the node.
Setting yourself up, minting access, and the production TLS/auth deployment are in
**[`ADMIN.md`](ADMIN.md)** and **[`docs/deployment.md`](docs/deployment.md)**.

## Docs & audit trail

- **[`QUICKSTART.md`](QUICKSTART.md)** — member setup (clone → open in VS Code → “onboard me”).
- **[`ADMIN.md`](ADMIN.md)** — run the shared substrate + register yourself + triage alpha tickets.
- **[`AGENTS.md`](AGENTS.md)** — read first if you’re an agent starting or organizing a project;
  routes to **[`lab-standard/`](lab-standard/)**, the playbook that scaffolds/conforms projects and
  promotes their work personal → shared WIP → consensus.
- **[`docs/decisions/`](docs/decisions/)** — Architecture Decision Records: *why* each choice was
  made, its alternatives, and the evidence. Start here for the rationale trail.
- **[`docs/architecture-overview.md`](docs/architecture-overview.md)** — a diagrammed walkthrough of the modules.
- **[`docs/related-work.md`](docs/related-work.md)** — verified prior-art map + honest novelty positioning.
- **[`docs/kg-schema-spec.md`](docs/kg-schema-spec.md)** — the reified-association KG schema.
- **[`CHANGELOG.md`](CHANGELOG.md)** — reverse-chronological change summary.

## Notes

- **Deliberate, not automatic.** Work becomes visible via `register_project`; findings become
  consensus via a reviewed `contribute_finding` → `graduate`. Nothing is promoted silently.
- **Attribution is automatic** — the shared node stamps every write with the member’s identity, so
  the lab always knows who did what.
- **The reference KG loads once per session** — the `demo` backend is tiny; use `hetionet` /
  `combined` for full mechanism queries.
- There is also a scriptable CLI research loop (`agent.py`, `LLM_BACKEND=anthropic`) for non-VS-Code
  use — see the docs; the MCP substrate above is the primary interface.
