# Project Structure & Naming — the shape every project takes

A project that follows this layout is *promotable by construction*: its artifacts already
carry the IDs, statuses, and provenance the shared WIP tier and the `contribute()` gate
expect. Deviating means someone (probably a future you) has to reshape it before the lab
can use it. Don't deviate.

## Directory layout

```
<project>/
├── CLAUDE.md              # dropped in from templates/project-CLAUDE.md — makes future
│                          #   sessions in THIS dir follow the standard automatically
├── README.md              # from templates/project-README.md — what/why/status
├── data/
│   ├── raw/               # READ ONLY. Source of truth. Never written by any agent.
│   ├── processed/         # cleaned / feature-engineered
│   └── external/          # reference sets, PRS weights, GWAS sumstats
├── hypotheses/            # one YAML per hypothesis:  H{NNN}_{slug}.yaml
├── experiments/
│   └── H{NNN}/
│       ├── config.yaml    # hyperparameters + run settings
│       ├── run.py         # standalone entry point (has __main__), NOT a notebook
│       ├── results/
│       │   ├── metrics.csv
│       │   └── figures/   # save BOTH .png and .pdf
│       ├── logs/run.log   # versions, seed, timestamps (reproducibility)
│       ├── validity.json  # interim orthogonal gate results (see experiment-workflow)
│       ├── tool_ledger.json   # ordered trace of scientific ops actually run
│       └── provenance.md  # how the experiment was FORMED and TESTED
├── reports/               # H{NNN}_evaluation.md — the evaluator's verdict (interpretation)
├── campaigns/             # {slug}.json — DAGs linking related experiments
├── notes/                 # LOCAL SEMANTIC: your in-progress thinking (private, un-promoted)
├── literature/            # notes from lit agents (biomedical/, ml_architecture/)
└── src/                   # shared, importable modules (not experiment-specific)
```

`notebooks/` is allowed for exploration only — never the entry point for a result.

## Naming rules (used by the tracking tools — follow exactly)

- **Hypotheses**: `hypotheses/H{NNN}_{slug}.yaml`, e.g. `H001_t2d_ad_shared_genes.yaml`.
  `NNN` is zero-padded and monotonic within the project. The `id:` field inside is `H{NNN}`.
- **Experiments**: `experiments/H{NNN}/` — the directory name **equals the hypothesis id**
  it tests. One hypothesis → one experiment dir. (Re-runs are new rows / seeds, not new dirs.)
- **Reports**: `reports/H{NNN}_evaluation.md`.
- **Campaigns**: `campaigns/{slug}.json`; nodes reference `experiment_id`s.

`list_active_work` and the audit resources (`provenance://H001`, `report://H001`, …) key
off exactly these names. A misnamed artifact is invisible to the shared tier.

## Status vocabulary (the promotion state machine)

Every hypothesis YAML carries a `status:`; this is how the shared WIP tier and future
sessions know what is safe to build on.

```
draft ─► approved ─► running ─► complete
   │         │           │          │
   └─────────┴───────────┴──────────┴──► abandoned   (record WHY in the report)
```

- `draft` — written, not yet reviewed/grounded. Do not implement.
- `approved` — reviewed by the hypothesis-planner, grounded/calibrated, pre-registered.
  Only now may `code-implementer` write code.
- `running` — an experiment dir exists and is executing (or mid-run).
- `complete` — evaluated; a `reports/H{NNN}_evaluation.md` exists with a verdict.
- `abandoned` — dropped; the report says why (failed validity gate, infeasible, refuted).

## Document tracking (what makes an artifact promotable)

Every research artifact must carry three things, or it cannot move up a tier:

1. **An ID** — `H{NNN}` / campaign slug. No orphan files.
2. **A status** — from the vocabulary above (hypotheses) or an explicit stage
   (experiments: `spec only` → `implemented/running` → `evaluated`).
3. **Provenance links** — what it derives from: KG paths, literature sources, prior
   `H{NNN}`s. Hypotheses record this in `provenance` fields; experiments in `provenance.md`.

Rule of thumb: **if it has a conclusion, it needs provenance before it can be shared.**
A note in `notes/` needs none (it is local semantic). The moment it becomes a hypothesis
or a result, it needs all three. See [`promotion.md`](promotion.md).
