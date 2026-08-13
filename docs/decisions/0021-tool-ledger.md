# ADR-0021: Per-run tool ledger (intended vs actual tool use)

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
The loop recorded *actual* orchestrator tool calls in episodic memory (`tools_called`),
but: (a) it was never surfaced or tied to an experiment, (b) there was no declaration of
what tools the agent *thought* it would need, (c) no plan-vs-actual comparison, and (d)
the specialist's internal skill calls weren't captured at all. So "what tools did the
agent intend, which did it actually use, in what order" was not an auditable artifact.

## Decision
Add **`tool_ledger.py`** — a `ToolLedger` (plan / record / diff / save / summary) that
records intended and actual tool calls, in order, per run, as JSON under
`memory/tool_ledgers/` (gitignored run data). Wire it into the two **code-controlled
reasoning agents**:
- **Orchestrator** (`agent.py`): a pre-flight `_plan_tools()` step (schema-constrained)
  makes the model declare the tools it expects to need, in order, with reasons →
  `ledger.plan()`. Each executed call is `ledger.record(..., layer="orchestrator")`. At
  the end the ledger is tied to the run id, saved, and a plan-vs-actual summary printed.
- **Specialist** (`specialist.py`): records its internal skill calls
  (`list_skills`/`read_skill`/`run_bash`, `layer="specialist"`) to its own ledger and
  returns a compact trace; the orchestrator ledger shows `run_specialist` as one call.
- **Experiment** (`experiments/{id}/run.py`): records the actual SCIENTIFIC/statistical
  operations it performs, in order (`layer="experiment"`) — data generation/fetch,
  per-gene tests, `multipletests`, effect sizes, plotting — to a tracked
  `experiments/{id}/tool_ledger.json`. This is the experimentation/testing layer.

## Rationale & evidence
- **Verified end-to-end** (demo KG, live Qwen): run-11 — intended `[find_paths,
  assess_hypothesis, calibrate_link, propose_experiment]`, actual `find_paths →
  assess_hypothesis → calibrate_link`, diff cleanly flags `propose_experiment` as
  planned-but-unused. Persisted to `memory/tool_ledgers/run-11.json`.
- **The ledger immediately surfaced a real calibration signal**: the local 14B initially
  *over-planned* (declared 11 intended tools, used 3). Tightening the plan prompt toward
  selectivity cut that to 4-vs-3 — the intended plan is now informative, not a dump of
  everything. This is exactly the introspection the ledger is for.
- **Experiment layer verified**: H001's `run.py` emitted `experiments/H001/tool_ledger.json`
  with the **17 scientific operations in order** — `generate_synthetic_expression →
  scipy.stats.ttest_ind → cohens_d → statsmodels.multipletests(bonferroni) →
  multipletests(fdr_bh)` across 3 seeds → `matplotlib.savefig`. The actual
  experimentation/testing tool calls are now an auditable per-experiment artifact.

## Boundary (honest scope)
Three of the four layers are captured: the orchestrator's intended-vs-actual, the
specialist's skill calls, and the experiment's scientific/statistical operations. The
**one remaining gap** is the four-agent *pipeline's* own harness tools — the
code-implementer's `Write`/`Edit` and the experiment-runner's `Bash` — which run as
harness subagents whose internal tool usage is telemetry, not capturable from repo code.
That "wrote/ran the code" layer is meta to the science; its provenance already lives in
each experiment's `run.log`, and stage order is deterministic. Instrumenting it would
require the harness to expose per-subagent tool traces.

## Consequences
- Every orchestrator run and every specialist invocation now has an auditable
  intended → actual → order → diff trace — the tool analogue of the reproducibility log.
- Ledgers are gitignored (per-run data); only the module + wiring ship.
- Pairs with the CLAUDE.md reproducibility standards and the experiment audit trail.
