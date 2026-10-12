"""Biology evaluation harness — measure the LLM backend's capability on biomedical tasks.

The agent (agent.py) is only as good as the model under it: a generated hypothesis can
be no more specific, plausible, or testable than the model that produced it. The rest of
the repo measures the *agent's* claims (confidence, KG grounding, the critic); this
harness measures the *model's* ceiling, and does it reproducibly and backend-agnostically
so the Claude-vs-Qwen question has a number instead of an opinion.

Design (ADR-0062):
  - backend-agnostic : every benchmark calls llm.py; `--backend` switches provider.
  - reproducible     : fixed seeds, versioned datasets (data/eval_datasets/), persisted
                       results (results/evals/<ts>_<backend>_<benchmark>.json).
  - honest           : metrics ship with bootstrap 95% CIs, not bare point estimates.
  - composable       : a benchmark is a module exposing run(backend) -> dict; adding one
                       is a dict entry, not a harness change.

CLI:
  python biology_evals.py --benchmark hypothesis_generation          # uses configured backend
  python biology_evals.py --backend anthropic --benchmark all
  LLM_BACKEND=ollama KG_BACKEND=hetionet python biology_evals.py --benchmark hypothesis_generation
  python biology_evals.py --compare results/evals/<a>.json results/evals/<b>.json

Benchmarks:
  hypothesis_generation : quality (plausibility / specificity / novelty / testability) of
                          the agent's KG-grounded hypotheses — the eval-driven-dev subject.
  literature_grounding  : fidelity to supplied abstracts (precision / recall / hallucination).

The KG-backed benchmarks read KG_BACKEND from the environment (demo | hetionet | monarch |
combined); a dataset records which backend its entities were validated against.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import llm
from evals import _dataset

RESULTS_DIR = Path(os.environ.get("EVAL_RESULTS_DIR", "results/evals"))

# name -> "module:function"; imported lazily so a missing optional dep or dataset for one
# benchmark never stops the others from running.
BENCHMARKS = {
    "hypothesis_generation": "evals.hypothesis_generation:run",
    "literature_grounding": "evals.literature_grounding:run",
}


def _resolve(name: str):
    mod_name, fn_name = BENCHMARKS[name].split(":")
    import importlib
    return getattr(importlib.import_module(mod_name), fn_name)


def _dataset_of(name: str):
    """The dataset filename a benchmark declares (its module's DATASET), or None."""
    import importlib
    mod = importlib.import_module(BENCHMARKS[name].split(":")[0])
    return getattr(mod, "DATASET", None)


def _seeded(name: str) -> bool:
    """A benchmark is runnable iff it declares no dataset or that dataset is seeded.
    Keeps an un-curated benchmark (e.g. literature_grounding) visibly PENDING rather than
    advertised as runnable — a grounding benchmark on invented data measures nothing (ADR-0062)."""
    ds = _dataset_of(name)
    return ds is None or _dataset.exists(ds)


def run_benchmark(name: str, backend: str = None) -> dict:
    """Run one benchmark, persist its result, print a one-line summary. Returns the result,
    or None (with an explanatory line) if the benchmark's dataset is not seeded yet."""
    if name not in BENCHMARKS:
        raise ValueError(f"unknown benchmark: {name}. options: {list(BENCHMARKS)}")
    if not _seeded(name):
        print(f"  PENDING {name}: dataset '{_dataset_of(name)}' not seeded yet — skipping. "
              f"See evals/README.md for its schema and how to curate it.")
        return None
    b = (backend or llm.BACKEND).lower()
    print(f"running {name} on backend={b} (KG_BACKEND={os.environ.get('KG_BACKEND', 'demo')}) ...")
    result = _resolve(name)(backend=backend)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    outpath = RESULTS_DIR / f"{ts}_{b}_{name}.json"
    outpath.write_text(json.dumps(result, indent=2))
    print(f"  saved {outpath}")
    print(f"  summary: {result.get('summary', '(see JSON)')}")
    return result


def compare(path_a: str, path_b: str) -> None:
    """Print an aligned metric table for two result files of the SAME benchmark."""
    a, b = json.loads(Path(path_a).read_text()), json.loads(Path(path_b).read_text())
    if a["benchmark"] != b["benchmark"]:
        raise ValueError(f"different benchmarks: {a['benchmark']} vs {b['benchmark']}")
    print(f"\n{a['benchmark']}:  {a.get('backend')} vs {b.get('backend')}")
    print("=" * 64)
    keys = list(dict.fromkeys(list(a["metrics"]) + list(b["metrics"])))
    for k in keys:
        print(f"  {k:<36} {str(a['metrics'].get(k, '—')):>11}  vs  "
              f"{str(b['metrics'].get(k, '—')):>11}")


def main() -> None:
    p = argparse.ArgumentParser(description="biology capability benchmarks for the LLM backend")
    p.add_argument("--backend", default=None,
                   help="llm backend override (ollama | anthropic); default = LLM_BACKEND")
    p.add_argument("--benchmark", default="all", choices=["all"] + list(BENCHMARKS))
    p.add_argument("--list", action="store_true",
                   help="list benchmarks and whether each one's dataset is seeded")
    p.add_argument("--compare", nargs=2, metavar=("FILE_A", "FILE_B"),
                   help="compare two result JSONs instead of running")
    args = p.parse_args()

    if args.list:
        for name in BENCHMARKS:
            status = "seeded" if _seeded(name) else "PENDING (dataset not seeded)"
            print(f"  {name:<24} dataset={_dataset_of(name) or '(none)':<32} {status}")
    elif args.compare:
        compare(*args.compare)
    elif args.benchmark == "all":
        for name in BENCHMARKS:
            run_benchmark(name, args.backend)        # pending benchmarks are skipped cleanly
    else:
        run_benchmark(args.benchmark, args.backend)


if __name__ == "__main__":
    main()
