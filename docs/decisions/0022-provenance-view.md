# ADR-0022: Unified per-experiment provenance view

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
By ADR-0020/0021 each experiment had scattered artifacts — a hypothesis spec, a config,
metrics, an evaluation report, a scientific-op tool ledger, a run log. Answering "how was
this hypothesis formed, and how was it tested?" meant opening six files. The two recent
questions (hypothesis *reasoning* + tool *ledgers*) converge on wanting one assembled view.

## Decision
Add **`provenance.py`** — a deterministic (no-LLM) assembler that reads an experiment's
own artifacts and stitches them into one card at `experiments/{id}/provenance.md`:
- **Hypothesis (framing)** — question, H₀/H₁, success metric, status (from the spec)
- **Formation** — method, data source, pre-registered decisions; plus a best-effort link
  to the orchestrator run ledger that formed it (term-overlap match)
- **Testing** — design (from config) + the ordered **scientific tool calls** (from the
  experiment's `tool_ledger.json`) + the statistical standards
- **Result** — metrics summary + the verdict extracted from the evaluation report
- **Audit trail** — paths to every underlying artifact

Run as `python provenance.py <id>`.

## Rationale & evidence
- **Verified on both experiments.** H001's card shows the 17-step synthetic pipeline
  (generate → ttest_ind → cohens_d → multipletests ×3 seeds → savefig) with the
  REJECT-H₀-on-synthetic verdict. H002's card shows the 13-step real-data pipeline
  (GEO fetch → collapse → OLS → multipletests → bootstrap → power → per-region →
  replication fetch → tech-rep collapse → OLS → direction replication → forest) with the
  FAIL-TO-REJECT-H₀ verdict. To emit H002's ledger, its `run.py` was instrumented like
  H001's and re-run (deterministic: same PPARGC1A/SOD1/APP discovery hits).
- **Deterministic by design** — it only *assembles* existing artifacts, so the card can't
  introduce new claims or drift from the underlying evidence.

## Consequences
- Every experiment now has a single "how formed / how tested" view tying the whole
  generate→test→interpret arc together, tracked in git alongside the experiment.
- Formation-trace linkage is best-effort today (term overlap); it becomes exact once a
  hypothesis is formed in an orchestrator run whose ledger is tagged with the experiment.
- Regenerable any time from artifacts (`python provenance.py <id>`).
