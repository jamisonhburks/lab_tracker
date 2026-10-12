# ADR-0062: Biology evaluation harness — measure the LLM backend's capability, not just the agent's

- **Date:** 2026-10-09
- **Status:** Accepted

## Context
Everything in this repo evaluates the *agent's* output: `confidence.py` scores evidence,
`kg.check_connection` grades grounding, `critic.py` adversarially verifies extracted
associations, `eval_critic.py` runs the critic against a labeled suite. None of it measures
the *model underneath*. That matters because the agent is bounded by its backend — a
generated hypothesis can be no more specific, plausible, or testable than the model that
wrote it, and a literature summary can be no more faithful than the model's tendency to
hallucinate. We can swap backends (`llm.py`: ollama/Qwen3-14B ↔ anthropic/Claude, ADR-0014),
but we had no number that says what that swap buys on *biomedical* tasks specifically.

The gap is concrete: when choosing whether a capability is ready to expose in a research
product, "the agent's confidence is calibrated" is necessary but not sufficient — the
ceiling is the model's biomedical competence, and that was unmeasured.

## Decision
Add `biology_evals.py` + an `evals/` package: a backend-agnostic benchmark harness that
measures the LLM on biomedical tasks the agent actually relies on, reproducibly and with
honest uncertainty.

- **A benchmark is a module** exposing `run(backend=None) -> dict`, registered by name in
  `biology_evals.BENCHMARKS`. Adding one is a dict entry, not a harness change.
- **Backend-agnostic** — benchmarks call `llm.py`, so `--backend anthropic` vs the default
  Qwen is one flag; the Claude-vs-Qwen question gets a number instead of an opinion.
- **Reproducible** — fixed seeds, datasets versioned in `data/eval_datasets/` (carved out of
  the `data/` gitignore because they are hand-labeled ground truth, not a regenerable cache),
  results persisted to `results/evals/<ts>_<backend>_<benchmark>.json`.
- **Honest** — metrics ship with percentile-bootstrap 95% CIs (`_scorer.bootstrap_ci`,
  numpy-only, no new dependency), never bare point estimates. A paired-bootstrap delta
  (`_scorer.paired_delta_ci`) supports before/after comparisons.
- **Judge reuse** — the LLM-as-judge (`_scorer.judge`) is the same doctrine `critic.py`
  already uses: one judge call is noisy, so run N and take the per-field median. It goes
  through `llm.parse`, so the judge's output is schema-validated with a retry on malformed
  JSON — not a raw `json.loads` that dies on a stray token.

First benchmark: `hypothesis_generation` (the subject of the ADR-0063 eval-driven-dev case
study). `literature_grounding` (hallucination fidelity against supplied abstracts) follows,
seeded from real publications.

## Rationale
- **Measures what the product needs:** specificity, testability, grounding, and hallucination
  are exactly the failure modes that make or break a biomedical research assistant.
- **Separates substrate signals from judged ones.** Grounding and novelty come from the KG
  and PubMed (`kg.check_connection`, `novelty.classify`), not the judge; only the genuinely
  subjective dimensions (specificity, testability) are judged. This keeps the
  circular-evaluation surface as small as possible.
- **Composable with what exists** rather than a parallel stack — it reuses `llm.py`,
  `schemas.py`/`llm.parse`, and the multi-vote pattern from `critic.py`.

## Consequences
- The harness adds no dependency beyond numpy (already pulled by semantic memory). Judge and
  CI math are local.
- Datasets are now a maintained artifact. `data/eval_datasets/*.jsonl` is version-controlled
  and must be curated from independent sources (PubMed, Cochrane, the lab's own papers), never
  from model output — a benchmark seeded from the model it judges is worthless.
- **Self-preference caveat (honest):** when the judged model and the judge model are the same
  family, the judge can flatter the generator. Mitigations: rubric-anchored prompts,
  multi-vote medians, and `EVAL_JUDGE_BACKEND` to run a cross-family judge. The case study
  states this limitation rather than hiding it.
- KG-backed benchmarks read `KG_BACKEND` from the environment; a dataset records which backend
  its entities were validated against (`research_questions_v1` → hetionet).

## Alternatives considered
- **Reuse `eval_critic.py` and call it done** — rejected: it tests the *critic's* accept/reject
  accuracy on a fixed suite, not the generator's hypothesis quality or grounding fidelity.
  Different question.
- **Adopt an external benchmark framework (lm-eval-harness, etc.)** — rejected for now: heavy
  dependency and generic tasks, when the point is a handful of *task-specific* biomedical evals
  wired to this repo's own primitives. Revisit if the suite grows.
- **Add scipy for the statistics** — rejected: a percentile bootstrap is a few lines of numpy,
  and numpy is already a dependency; adding scipy for one correlation would be gratuitous.
