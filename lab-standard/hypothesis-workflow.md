# Hypothesis Workflow — generate → ground → pre-register

A hypothesis is not "a good guess." In this lab it is a **pre-registered, grounded,
calibrated, novelty-checked** claim written down *before* any code is run, so that the
result — positive or negative — is interpretable and promotable. This file is the recipe.

Use the substrate throughout (see [`using-the-substrate.md`](using-the-substrate.md)); a
bare session's intuition is exactly what the substrate exists to check.

## 1. State the link as subject → predicate → object

Reduce the idea to a testable relation between two entities, e.g.
`type 2 diabetes —shares_genetic_risk→ Alzheimer's disease`. If you cannot phrase it this
way, it is a research *direction*, not yet a hypothesis — keep it in `notes/`.

## 2. Ground it (is there a mechanism, or is this a leap?)

- `ground_claim(subject, object)` → `grounded | weakly_grounded | novel_unverified | off_graph`.
- `find_paths(subject, object)` → the actual A→B→C chains and their sources — the
  mechanistic evidence you will cite as provenance.

**`novel_unverified` is not a failure.** It means the trustworthy KG has no path yet — a
genuinely new hypothesis. But say so explicitly, and expect to have to *establish* the
link before testing mechanism (the experiment plan will differ — see propose_experiment).

## 3. Calibrate it (is the support real, or a hub artifact?)

- `calibrate_link(subject, object)` → percentile / empirical p-value against a
  **degree-preserving permutation null**. A high raw realism score that is *typical of
  random degree-matched pairs* is density, not signal. Record the percentile.

## 4. Check novelty (are you about to rediscover a known result?)

- `check_novelty(subject, object, via=<bridge>)` → `bridge_published | emerging_bridge |
  novel_bridge | novel_juxtaposition` from PubMed co-mention counts.
- If **published**: this is confirmation, not discovery. Either pivot to an unexamined
  facet, or state up front that the contribution is replication/validation. Don't dress a
  rediscovery as novel — the critic gate will catch it, and so will reviewers.
- Also run `list_active_work` and `recall_prior_work` — has the lab or a past you already
  tried this? Negatives count; don't repeat a dead end without a reason.

## 5. Derive the test plan

- `propose_experiment(subject, object, hypothesis=...)` → the study design, data, and
  statistical tests implied by the mechanism types on the paths, **plus** KG-grounded ML
  methods when a data modality is implicated (`recommend_methods` under the hood). This
  becomes the `method:` and `success_metric:` of the YAML — don't hand-wave them.

## 6. Write the pre-registration YAML

Copy [`templates/hypothesis.yaml`](templates/hypothesis.yaml) to
`hypotheses/H{NNN}_{slug}.yaml` and fill **every** field. Non-obvious ones:

- `null_hypothesis` / `alternative_hypothesis` — write H₀ and H₁ explicitly. If you can't
  state H₀, you can't test it.
- `success_metric` — the primary metric **and the threshold** for claiming success,
  decided *now*, before seeing data. Include the correction you will apply.
- `min_runs` — ≥3 for any stochastic method (lab standard).
- `provenance` — the KG paths (Step 2), the calibration percentile (Step 3), the novelty
  verdict (Step 4), and any prior `H{NNN}` this builds on. This is what makes the eventual
  finding promotable.
- `validity_gates` — the interim, hypothesis-*orthogonal* checks the run must pass (cohort
  integrity, data scale, negative/positive controls). See
  [`experiment-workflow.md`](experiment-workflow.md); list them here so they are pre-committed.
- `status: draft`.

## 7. Get it approved (separation of concerns)

Approval is a distinct role. Invoke the **`hypothesis-planner`** agent to review and
formalize; only it flips `status: draft → approved`. Do not implement a `draft`. The
planner does not write code; the implementer does not interpret; the evaluator does not
re-run — this separation is what keeps results honest (see the experiment workflow).

## The statistical standards are not optional

`p < 0.05`; report **both** Bonferroni and Benjamini-Hochberg FDR when >1 hypothesis is
tested simultaneously; always report **effect size** (Cohen's d / η² / AUC); **≥3 runs**
for stochastic experiments; never call a result significant without naming the correction.
Bake these into `success_metric` now so the evaluator can hold you to them later.

## Definition of done

- [ ] Link stated as subject–predicate–object.
- [ ] Grounding, calibration percentile, and novelty verdict recorded in `provenance`.
- [ ] `list_active_work` + `recall_prior_work` checked for duplication / prior negatives.
- [ ] Every YAML field filled, including H₀/H₁, thresholded success_metric, min_runs, gates.
- [ ] `hypothesis-planner` approved it (`status: approved`) before any code exists.
