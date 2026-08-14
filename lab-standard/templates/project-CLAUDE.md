# CLAUDE.md — {{PROJECT_TITLE}}

**This project conforms to the lab shared-knowledge standard.** You are an agent working
inside a single research project that is part of a larger lab substrate. Before doing
anything, understand where you are and which rules bind you.

## Read these first (they are the source of truth, not this file)

The standard lives in the lab substrate repo. Point these at your local checkout:

- Playbook index: `{{SUBSTRATE_PATH}}/lab-standard/START-HERE.md`
- Forming a hypothesis: `{{SUBSTRATE_PATH}}/lab-standard/hypothesis-workflow.md`
- Implement / run / evaluate: `{{SUBSTRATE_PATH}}/lab-standard/experiment-workflow.md`
- Sharing conclusions: `{{SUBSTRATE_PATH}}/lab-standard/promotion.md`
- Layout & naming: `{{SUBSTRATE_PATH}}/lab-standard/project-structure.md`
- Querying shared knowledge: `{{SUBSTRATE_PATH}}/lab-standard/using-the-substrate.md`

Do not reconstruct these rules from memory — open the file for what you're doing.

## What this project is

{{One-line question + modality. Keep in sync with README.md.}}

## The rules that bind every session here

**Tiers — move your work up, never skip a gate.**
`local semantic` (notes/, private) → `shared WIP` (hypotheses/experiments/, tracked,
provisional) → `shared consensus` (curated findings, critic-gated via `contribute_finding`).
Process is shared early; conclusions are gated. See `promotion.md`.

**Separation of concerns.** hypothesis-planner *approves* → code-implementer *writes* →
experiment-runner *executes* → results-evaluator *interprets*. Don't collapse these roles;
the separation is what keeps results honest. Don't implement a `draft` hypothesis.

**Structure.** Follow `project-structure.md` exactly: `H{NNN}_{slug}.yaml` hypotheses;
`experiments/H{NNN}/` mirrors the hypothesis id; standard subpaths (`config.yaml`,
`run.py` with `__main__`, `results/metrics.csv`, `logs/run.log`, `validity.json`,
`tool_ledger.json`, `provenance.md`); `reports/H{NNN}_evaluation.md`. Names are how the
shared tier finds your work — a misnamed artifact is invisible.

**Ground before you commit.** Use the substrate (`ground_claim`, `find_paths`,
`calibrate_link`, `check_novelty`, `list_active_work`, `query_curated_findings`) before
approving a hypothesis, so you don't chase hub artifacts, rediscover known results, or
duplicate in-flight work.

**Provenance is the toll to consensus.** Record how each hypothesis was formed and each
result was tested, as you go. You cannot `contribute_finding` without it.

## Non-negotiables (inherited from the lab — never override)

- `data/raw/` is **read-only**. Never write to it. Never write code that re-identifies
  individuals or emits row-level patient data to unprotected locations. Local-first.
- `p < 0.05`; report **both** Bonferroni and Benjamini-Hochberg FDR when >1 hypothesis is
  tested; always report **effect size**; **≥3 runs** for stochastic experiments; never
  call a result significant without naming the correction.
- Every run logs Python + key package versions, seed, and start/end timestamps.
- Entry points are standalone `run.py` scripts with a `__main__` block, not notebooks.
  Don't hardcode absolute paths; import shared logic from `src/`.
