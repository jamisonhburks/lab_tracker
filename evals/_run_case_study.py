"""Driver for the ADR-0063 eval-driven-dev case study: run baseline vs 'testable' over the
full research_questions dataset and persist the paired report. Invoked from the CLI, not imported.

  KG_BACKEND=hetionet LLM_BACKEND=ollama EVAL_JUDGE_VOTES=3 python -m evals._run_case_study
"""

import json
import os
from datetime import datetime
from pathlib import Path

import llm
from evals import hypothesis_generation as hg


def main() -> None:
    rep = hg.eval_driven_dev()
    out = Path("results/evals")
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = out / f"{ts}_{llm.BACKEND}_hypothesis_generation_edd.json"
    path.write_text(json.dumps(rep, indent=2))

    print("SAVED:", path)
    print("SUMMARY:", rep["summary"])
    for dim in ("composite", "specificity", "testability", "grounding_score"):
        b, i, d = rep["baseline"][dim], rep["intervention"][dim], rep["paired_delta"][dim]
        print(f"  {dim:<15} baseline={b['mean']} {b['ci']}  ->  "
              f"intervention={i['mean']} {i['ci']}   "
              f"Δ={d['delta']} CI={d['ci']} p={d['p_two_sided']}")
    print("  grounding baseline:", rep["baseline"]["grounding_dist"])
    print("  grounding intervention:", rep["intervention"]["grounding_dist"])
    print("  n:", rep["n"], "judge_backend:", rep["judge_backend"], "votes:", rep["judge_votes"])


if __name__ == "__main__":
    main()
