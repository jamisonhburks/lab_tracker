"""evals — biology capability benchmarks for the research agent's LLM backend.

The agent's output is bounded by the underlying model: a hypothesis can be no more
specific, plausible, or testable than the model that wrote it. The rest of the repo
evaluates the *agent's* claims (confidence scoring, KG grounding, the adversarial
critic); this package evaluates the *model* on biomedical tasks, so the ceiling is
measured, not assumed.

Each benchmark is a module exposing `run(backend=None) -> dict` and is driven by the
`biology_evals.py` CLI. Benchmarks are backend-agnostic (they call `llm.py`, so a
Claude-vs-Qwen comparison is one env var), seeded from versioned datasets in
`data/eval_datasets/`, and persist timestamped results to `results/evals/`.

Shared machinery lives in `_scorer.py` (LLM-as-judge + bootstrap CIs) and
`_dataset.py` (dataset loading). See ADR-0062.
"""
