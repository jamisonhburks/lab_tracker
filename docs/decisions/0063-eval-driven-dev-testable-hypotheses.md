# ADR-0063: Eval-driven development — the 'testable' hypothesis intervention, measured

- **Date:** 2026-10-12
- **Status:** Accepted

## Context
ADR-0062 built a harness to put a number on the backend's biomedical competence. The first
use of that number is a methodology test: can we improve the agent by writing an eval
*first*, letting it name a specific weakness, making one targeted change, and confirming the
change helps *on the same items* — instead of shipping a prompt tweak and eyeballing a few
outputs? Baseline `hypothesis_generation` on qwen3:14b scored **testability = 1.0/2.0**: the
model reliably *implies* a prediction but almost never commits to a concrete, refutable
experiment. That is a measurable, nameable deficiency, not a vibe — exactly the kind of thing
the harness exists to surface.

## Decision
Run the eval-driven-development loop end-to-end and record it as a worked example:

1. **Metric first.** The testability rubric (0–2; `2` requires a SPECIFIC refutable prediction
   AND a concrete experiment — design + measured variable + comparison) is defined in the
   harness (`evals/hypothesis_generation.py`) *before* any change to generation.
2. **One targeted intervention.** The `'testable'` generation variant
   (`agent.synthesize_hypothesis(variant='testable')` + the `HypothesisTestable` schema): the
   prompt now REQUIRES a `falsifiable_prediction` and an `experiment`. The baseline decode is
   left byte-for-byte unchanged, so the comparison isolates the one change.
3. **Paired re-measure.** `eval_driven_dev()` scores baseline and `testable` on the SAME 18
   items, 3 judge votes each, and reports a paired-bootstrap delta with a 95% CI and p.

## Results
**Config:** backend `ollama/qwen3:14b`; judge = same backend, `votes=3`; dataset
`research_questions_v1` (n=18, hetionet-validated); run **2026-10-09**, persisted to
`results/evals/20261009T215350_ollama_hypothesis_generation_edd.json`.

| Dimension | Baseline | Testable | Δ (95% CI) | p (2-sided bootstrap) |
|---|---|---|---|---|
| **composite** (mean of spec, test) | 1.000 | 1.667 | **+0.667** [0.556, 0.778] | 0.0 |
| specificity | 1.000 | 1.333 | +0.333 [0.111, 0.556] | 0.001 |
| testability | 1.000 | 2.000 | +1.000 [1.000, 1.000] | 0.0 |
| grounding *(guardrail)* | 1.722 | 1.722 | 0.000 | — |

`n_ok = 18/18` both variants (no generation failures). Grounding distribution unchanged:
13 grounded / 5 weakly-grounded under both variants. `p = 0.0` means no bootstrap replicate
(of 2000) landed on the zero side of the delta.

**Concrete example — `rq002`, type 2 diabetes mellitus ↔ Alzheimer's disease.** Baseline named
OGG1/SOD1 as shared intermediaries but offered no way to test the claim (judge: *"implies
observable predictions … but does not provide a concrete experiment with a design, measured
variable, or comparison"* → testability 1). The `testable` variant added a refutable
prediction and an **OGG1-knockdown vs. wild-type** experiment measuring amyloid-β and cognitive
performance (→ testability 2), promoted the intermediates to `high` centrality, and surfaced
APOE (specificity 1→2). The same 1→2 jump on both dimensions recurred across the disease–disease
pairs (`rq003`, `rq005`, `rq012`, `rq015`, `rq016`).

## Rationale / interpretation
- **testability 1.0 → 2.0, CI [1.0, 1.0].** The intervention did exactly one thing and did it
  completely: every item now carries a concrete experiment. A tight CI at the ceiling is the
  signature of a well-targeted change, not a diffuse one.
- **specificity +0.333, CI [0.111, 0.556], p=0.001.** A smaller, real side-benefit — forcing an
  experiment nudges the model toward naming the molecules that experiment would measure.
- **grounding held (Δ=0).** The guardrail did its job: the change bought testability WITHOUT
  trading away KG grounding or inventing off-graph entities — the failure mode we most feared
  (a model that gets "more testable" by making things up). This is why grounding is reported as
  a guardrail, never folded into the quality score.
- **composite +0.667, CI [0.556, 0.778].** The CI excludes zero by a wide margin on n=18 — the
  headline the case study claims.

## Consequences
- `'testable'` becomes the recommended variant of the hypothesis tool when the user wants an
  *actionable* hypothesis; `baseline` is retained for byte-identical reproducibility and a
  cheaper decode.
- The harness paid for itself on first use: it converted "the hypotheses feel hand-wavy" into
  "testability = 1.0, here is the one-line fix, here is +1.0 with a CI at the ceiling."
- **Limitations (stated, not hidden):**
  - *Self-preference.* Judge and generator are both qwen3:14b; no Anthropic key was available
    for a cross-family judge (`EVAL_JUDGE_BACKEND`). Pairing on a shared judge cancels much of a
    *constant* bias in the delta, but not interaction bias, and the *absolute* testability level
    may be flattered. A cross-family or human spot-check is the real fix (ADR-0062).
  - *Scope of the interval.* n=18, one backend; the CI reflects item-to-item variance, not model
    or seed variance (Qwen generation is unseeded, so exact numbers will drift on a re-run).
  - *Form, not truth.* The judge scores the TEXT. A concrete-looking experiment is not a correct
    or feasible one — testability measures whether a claim is refutable as written, not whether
    the biology is right. That is a separate benchmark (`literature_grounding`) and separate work.

## Alternatives considered
- **Ship the prompt change and eyeball a handful of outputs** — rejected: that is precisely the
  un-measured iteration ADR-0062 exists to replace.
- **Fold grounding into the composite quality score** — rejected: grounding is grounded by
  construction (KG-constrained generation), so averaging it in would let a stable grounding floor
  mask a testability regression. It stays a guardrail.
- **Report only the point deltas** — rejected: bare deltas are the overclaiming this repo avoids;
  a paired-bootstrap CI and p ship with every number.
