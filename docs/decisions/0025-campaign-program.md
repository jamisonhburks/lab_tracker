# ADR-0025: Campaign / program object — experiment lineage + planner

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
Experiments are (deliberately) atomic and immutable (ADR-0020/0024) — you can't let
results reshape a running analysis without p-hacking. But real research *is* adaptive:
a null result should inform what you run next. That adaptivity needs a home *above* the
experiment, so "update the longer experiment plan" means appending a new experiment, not
mutating one.

## Decision
Add **`campaign.py`** — a `Campaign` is a **lineage (DAG) of atomic experiments** stored
at `campaigns/{name}.json`:
- each node = an experiment + its parent + the reason it was spawned + its verdict
  (auto-synced from the evaluation report);
- **`next_step()`** is a planner: it reads the latest completed experiment's verdict and
  the evaluator's own "Recommended next steps", and (LLM-assisted, local) proposes ONE
  concrete next atomic experiment — a draft hypothesis seed needing human approval.

"Update the plan" = **append a node**; a running experiment is never mutated. Every
plan-change is auditable (the DAG records *why* H002 followed H001).

## Rationale & evidence
- **Verified** — the `t2d-ad-shared-genes` campaign built from the completed H001 → H002
  lineage (auto-pulled verdicts: H001 synthetic success, H002 real-data null). Its
  planner, from H002's verdict + the evaluator's recommendations, proposed **H003**:
  "Replication in a larger, cell-type-aware cohort — ROSMAP snRNA-seq (n≈1,000 neurons),
  cell-type-specific to increase power and avoid bulk dilution, focused on the
  brain-expressed genes (IDE/AKT1/APOE/PPARGC1A)" — tagged *draft, needs human approval*,
  and *"do NOT mutate H002."*
- **Closes the evaluator → next-experiment loop** honestly: the interpretation agent's
  recommendations become the planner's input; the human `draft→approved` gate (as H002
  used) decides whether the proposal becomes a real experiment.

## Consequences
- Experiments stay atomic/reproducible; the research *program* is an auditable lineage.
- This is the safe answer to "evaluate against memory and update the plan": validity
  gates catch machinery bugs *inside* an experiment (ADR-0024); the campaign planner
  drives *what to run next* from verdicts + memory, one approved atomic experiment at a
  time.
- The campaign is a natural shared-lab object later (multi-user): a program many people
  contribute experiments to, with the KG/curated findings as the shared substrate.
