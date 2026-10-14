# Biology eval datasets

The benchmarks in this package (see [ADR-0062](../docs/decisions/0062-biology-evals.md)) read
hand-labeled ground-truth datasets from [`data/eval_datasets/`](../data/eval_datasets/) — JSONL,
one item per line, version-controlled (carved out of the `data/` gitignore) because they are
curated ground truth, not a regenerable cache.

**The one rule:** datasets are curated from independent sources (PubMed, Cochrane, the lab's own
papers) and **never from model output.** A benchmark seeded from the model it judges measures
nothing. Accordingly `literature_grounding_v1` holds only REAL, verbatim PubMed abstracts (fetched
via the no-LLM `deep_search._pubmed` path) with human-reviewed labels — never placeholder or
model-authored text, which would make the grounding number meaningless.

## Status

| Benchmark | Dataset | State |
|---|---|---|
| `hypothesis_generation` | `research_questions_v1.jsonl` (n=18) | ✅ seeded — hetionet-validated |
| `literature_grounding` | `literature_grounding_v1.jsonl` (n=4, pilot) | ✅ seeded — verbatim PubMed abstracts + PMIDs, labels human-reviewed; **expand beyond n=4** |

Check at any time:

```sh
python biology_evals.py --list
```

A pending benchmark is skipped with an explanatory line (not a crash); `--benchmark all` runs
whatever is seeded and reports the rest as `PENDING`.

## Schemas

### `research_questions_v1.jsonl` — for `hypothesis_generation`

```json
{"id": "rq001",
 "entity_a": "type 2 diabetes mellitus",
 "entity_c": "coronary artery disease",
 "question": "Through what shared mechanism does type 2 diabetes raise CAD risk?",
 "domain": "cardiometabolic",
 "expected_grounding": "grounded"}
```

`entity_a`/`entity_c` must resolve in the KG backend the dataset was validated against
(`research_questions_v1` → hetionet; `KG_BACKEND=hetionet`).

### `literature_grounding_v1.jsonl` — for `literature_grounding` (to curate)

```json
{"id": "lg001",
 "hypothesis": "the claim the model is asked to assess strictly against the abstracts",
 "abstracts": ["VERBATIM real abstract text [1]", "VERBATIM real abstract text [2]"],
 "ground_truth": [{"claim": "a finding the abstracts genuinely support"}],
 "distractor_claims": ["a true-sounding statement the abstracts do NOT support"],
 "source": {"pmids": [########, ########], "note": "provenance — not read by the scorer, kept for audit"}}
```

- **Required:** `hypothesis`, `abstracts` (abstract indices are 1-based, matching the `[n]`
  citations the model is asked to produce).
- **Optional but recommended:** `ground_truth` (drives `recall` — the supported findings the
  model should surface), `distractor_claims` (drives `distractor_endorsement` — planted
  true-sounding-but-unsupported claims that catch false endorsement), `id`, `source`.
- Metrics computed: `precision` / `hallucination_rate` (are the model's *cited* claims actually
  in the cited abstract), `recall`, `distractor_endorsement`.

**Curation guidance (so the ground truth is trustworthy):** paste abstracts verbatim from the
source; record PMIDs; write each `ground_truth.claim` and `distractor_claims` entry from a
first-hand reading of *those* abstracts, not from background knowledge — the whole point is that
the labels are independently correct, so they should get human review before the benchmark's
numbers are reported.

## Running

```sh
KG_BACKEND=hetionet LLM_BACKEND=ollama python biology_evals.py --benchmark hypothesis_generation
python biology_evals.py --backend anthropic --benchmark all      # needs ANTHROPIC_API_KEY
python biology_evals.py --compare results/evals/<a>.json results/evals/<b>.json
```

The eval-driven-dev case study (baseline vs the `testable` variant, [ADR-0063](../docs/decisions/0063-eval-driven-dev-testable-hypotheses.md)):

```sh
KG_BACKEND=hetionet LLM_BACKEND=ollama EVAL_JUDGE_VOTES=3 python -m evals._run_case_study
```
