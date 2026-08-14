# Using the Substrate — the MCP tools a session thinks *with*

The substrate is exposed over an **MCP server** (`mcp_server.py`), so an external Claude
session (Claude Desktop / Claude Code) can call it as tools. This is how a project talks to
the shared knowledge. Everything below is a tool or resource you call — you supply the
thinking; the substrate supplies grounding, calibration, novelty, recall, audit, and the
write-path you can't do from a bare session.

## Connect it

The server runs in one of three **scopes** (`SUBSTRATE_SCOPE=personal | shared | all`).
Run two deployments and add both to your MCP client config:

```jsonc
{"mcpServers": {
  "lab-shared":  {"command": "python", "args": ["/ABS/PATH/mcp_server.py"],
                  "env": {"SUBSTRATE_SCOPE": "shared", "KG_BACKEND": "combined"}},
  "my-personal": {"command": "python", "args": ["/ABS/PATH/mcp_server.py"],
                  "env": {"SUBSTRATE_SCOPE": "personal"}}}}
```

`shared` serves the lab's consensus + WIP (host it beside the git-repo KG); `personal`
serves only *your* episodic + semantic memory (local, private). The server holds **no LLM**
— it is a store, not a thinker. It emits associations / grounding / aggregates, never
row-level patient data.

If MCP isn't wired up, the same functions exist as plain modules (`kg_memory`,
`hypothesis_tools`, `novelty`, `contribute`, …) — but the standard assumes the MCP surface,
because that's what makes projects interoperable.

## SHARED tier — query consensus + see WIP

| Tool | Use it to… |
|---|---|
| `ground_claim(subject, object)` | grade KG support: grounded / weakly / novel_unverified / off_graph |
| `find_paths(a, c, max_hops)` | get the A→B→C mechanistic chains + sources behind a link |
| `query_kg(entity)` | list an entity's typed neighbors with sources |
| `assess_hypothesis(a, c)` | degree-weighted realism (heuristic, comparative) |
| `calibrate_link(a, c)` | percentile / p-value vs a degree-preserving permutation null |
| `check_novelty(a, c, via)` | published vs new juxtaposition (PubMed co-mention counts) |
| `propose_experiment(a, c, hypothesis)` | infer data, design, tests + KG-grounded ML methods |
| `recommend_methods(target)` | traverse the fused ML graph for architectures/losses/metrics/caveats |
| `query_curated_findings(subject, object)` | what the lab has **concluded** (confidence-scored) |
| `list_active_work()` | the **WIP** window: every tracked hypothesis/experiment/campaign + status |
| `contribute_finding(...)` | the **write-path** into consensus (critic-gated — see promotion.md) |
| `review_queue()` | contributions awaiting human review (novel / contradictory) |

Audit **resources** (read the actual artifacts): `substrate://index`,
`provenance://{exp_id}`, `report://{exp_id}`, `ledger://{exp_id}`, `hypothesis://{hyp_file}`.

## PERSONAL tier — your own history (private)

| Tool | Use it to… |
|---|---|
| `recall_prior_work(query)` | your episodic memory: tried before? what happened (incl. negatives)? |
| `search_notes(query)` | your personal semantic distillations — *not* lab consensus |

## When to reach for which (map to the workflows)

- **Starting / scoping** → `list_active_work`, `query_curated_findings`, `recall_prior_work`
  (don't duplicate; don't rediscover). See [`new-project.md`](new-project.md).
- **Forming a hypothesis** → `ground_claim`, `find_paths`, `calibrate_link`, `check_novelty`,
  `propose_experiment`. See [`hypothesis-workflow.md`](hypothesis-workflow.md).
- **Auditing a past result** → the `provenance://` / `report://` / `ledger://` resources.
- **Sharing a conclusion** → `contribute_finding`, then `review_queue`. See
  [`promotion.md`](promotion.md).

## The honesty rules baked into these tools

- **Absence of KG support ≠ false.** `novel_unverified` / `off_graph` means unproven, not
  wrong — the KG is incomplete. Treat novelty as a candidate, not a refutation.
- **A high realism score is not a probability.** It's a comparative heuristic; only
  `calibrate_link` tells you if it beats degree-matched random.
- **Novelty ≠ correctness.** `check_novelty` tells you if something is *new*, not if it's *true*.
- **Consensus is gated; process is not.** Reading `list_active_work` shows provisional WIP;
  reading `query_curated_findings` shows gated beliefs. Don't conflate them.
