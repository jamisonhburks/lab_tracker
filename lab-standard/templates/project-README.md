# {{PROJECT_TITLE}}

> Status: `scaffolding | active | paused | complete`   ·   Modality: `{{tabular | ehr-events | ehr-tabular | waveform | genomic | ml-methods | mixed}}`
> Conforms to the lab standard — see `CLAUDE.md` (in this dir) and the substrate's
> `lab-standard/` playbook. Grounded/promoted through the shared substrate MCP server.

## Question

{{One or two sentences: the scientific question this project asks and why it matters.}}

## Status at a glance

| Hypothesis | Title | Status | Report |
|---|---|---|---|
| H001 | {{...}} | draft \| approved \| running \| complete \| abandoned | `reports/H001_evaluation.md` |

_(Keep this table current — it is the human-readable mirror of what `list_active_work`
surfaces to the shared WIP tier.)_

## Layout

Standard lab project layout (see `lab-standard/project-structure.md`):
`hypotheses/` · `experiments/H{NNN}/` · `reports/` · `campaigns/` · `notes/` (local,
private) · `data/{raw(read-only),processed,external}/` · `src/` · `literature/`.

## How this project connects to the lab

- **Grounding & novelty**: checked against the shared substrate before any hypothesis is
  approved (`ground_claim`, `calibrate_link`, `check_novelty`).
- **WIP visibility**: hypotheses/experiments here are tracked as shared *process* so the
  lab doesn't duplicate them (`list_active_work`).
- **Consensus**: concluded, gate-clean findings are promoted via `contribute_finding`
  (critic-gated) — see `lab-standard/promotion.md`. Nothing reaches consensus un-gated.

## Working here

Any session in this directory: read `CLAUDE.md` first, then the relevant workflow —
`hypothesis-workflow.md`, `experiment-workflow.md`, or `promotion.md`. Keep de-identified
data on-device; never write to `data/raw/`; apply the lab statistical standards (p<0.05,
Bonferroni + BH FDR, effect sizes, ≥3 runs, reproducibility logging).
