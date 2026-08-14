# Experiment Workflow — implement → run → evaluate

Once a hypothesis is `approved`, testing it is a **three-role pipeline with deliberate
separation of concerns**. The same session may drive all three, but treat them as
different hats — and prefer the dedicated agents, because the separation is what stops a
session from grading its own homework.

| Role | Agent | Does | Must NOT |
|---|---|---|---|
| implement | `code-implementer` | write a runnable `experiments/H{NNN}/` from the YAML | run it, or interpret |
| run | `experiment-runner` | execute, monitor, log results + reproducibility | interpret results |
| evaluate | `results-evaluator` | interpret metrics vs the pre-registered plan | re-run or edit anything |

## 1. Implement (`code-implementer`)

Input: the approved `hypotheses/H{NNN}_*.yaml`. Output: a complete, runnable directory
(see [`project-structure.md`](project-structure.md)):

- `config.yaml` — hyperparameters, seed, and the **pre-committed** success threshold.
- `run.py` — standalone, with a `if __name__ == "__main__":` block. Reads from relative
  paths; **never** writes to `data/raw/`; imports shared logic from `src/`.
- Wire in the **validity gates** as interim checks the run itself evaluates (Step 2).
- Emit `results/metrics.csv` and figures as **both** `.png` and `.pdf`.

The implementer builds exactly what the YAML specifies — it does not "improve" the
hypothesis. If the spec is untestable, kick it back to the hypothesis workflow.

## 2. Validity gates — the orthogonal safety checks (this is the part people skip)

Validity gates are **interim, hypothesis-orthogonal** checks: they test whether the
*experiment is even capable of answering the question*, independent of whether H₁ is true.
They catch the failure modes that silently invalidate a result. Write results to
`experiments/H{NNN}/validity.json`. Standard gates:

- **cohort_integrity** (`halt`) — labels well-formed, groups non-empty, no leakage between
  train/test, outcome coded as expected. A failure **halts** the run — a broken cohort
  can't answer anything. (This is the gate that catches the classic GEO gotcha of a label
  coded `AA` instead of `AD`.)
- **data_scale** (`flag`) — value ranges/units sane for the modality (e.g. log2 expression
  shouldn't max out at 59). Flags anomalies without halting.
- **negative_control** — a relation that *should* show nothing; if it "works," your
  pipeline is leaking signal.
- **positive_control** — a relation that *should* reproduce a known effect; if it doesn't,
  your pipeline lacks power to detect anything.

Gates are **pre-committed in the hypothesis YAML** (`validity_gates:`) so they can't be
chosen post-hoc to flatter the result. An honest `flag` you didn't expect is a finding —
record it, don't tune the threshold to make it disappear.

## 3. Run (`experiment-runner`)

- Execute `run.py`. Respect `min_runs` (≥3 for stochastic methods) with distinct seeds.
- Log to `logs/run.log`: Python version, key package versions (torch, sklearn, statsmodels,
  numpy, pandas), the seed(s), and start/end timestamps. Use `src/utils/log_run_metadata()`
  if present; otherwise log manually. This is the reproducibility floor — no exceptions.
- Record the ordered scientific operations to `tool_ledger.json` (intended vs actual), so
  the run is auditable via `ledger://H{NNN}`.
- If a `halt` gate trips, stop and report — do **not** push through a broken cohort.

The runner reports what happened; it does not say what it *means*.

## 4. Provenance card

Write `experiments/H{NNN}/provenance.md`: how the experiment was **formed** (the KG paths,
calibration, novelty verdict, prior `H{NNN}`s from the hypothesis) *and* **tested** (data
version, gates, seeds, tools). This is the deterministic audit trail the shared tier
exposes at `provenance://H{NNN}`. A finding without a provenance card cannot be promoted.

## 5. Evaluate (`results-evaluator`)

Input: `metrics.csv`, `validity.json`, `logs/`, and the pre-registered YAML. Output:
`reports/H{NNN}_evaluation.md`. The evaluator:

- Compares results to the **pre-committed** `success_metric` and threshold — not a moved goalpost.
- Applies the corrections named in the hypothesis (Bonferroni **and** BH FDR when >1 test)
  and reports **effect size** with the p-value. Names the correction every time.
- Reads the validity gates: a passed hypothesis test on top of a failed/flagged gate is
  **not** a clean result — say so.
- Weighs **negative results honestly**: an underpowered null is `promising_but_poorly_tested`,
  not "no effect." Power matters; a null from n=12 means little.
- Sets the hypothesis `status: complete` (or `abandoned`, with the reason).

The evaluator reads and interprets only — it never re-runs or edits code. If it thinks the
experiment was wrong, that goes in the report as a recommendation for the next hypothesis.

## Then: decide promotion

A `complete` experiment with a defensible, gate-clean finding is a **consensus candidate**.
Take it to [`promotion.md`](promotion.md) and `contribute_finding`. A negative or
gate-flagged result still promotes as **WIP** (it's tracked process) — and its honest
negative is exactly the kind of thing that saves the next session a wasted run.

## Definition of done

- [ ] `experiments/H{NNN}/` runs standalone; never writes `data/raw/`.
- [ ] `validity.json` present; any `halt` gate respected; flags recorded honestly.
- [ ] `logs/run.log` has versions + seed(s) + timestamps; `min_runs` satisfied.
- [ ] `tool_ledger.json` + `provenance.md` written.
- [ ] `reports/H{NNN}_evaluation.md` applies the pre-committed metric + both corrections +
      effect size; hypothesis `status` updated.
