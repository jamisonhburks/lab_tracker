"""_dataset — load versioned eval datasets from data/eval_datasets/.

Datasets are JSONL (one item per line) so they diff cleanly and append without
rewrites — the same store shape the rest of the repo uses. Each benchmark owns its
schema; this module only resolves paths and reads/validates the lines.
"""

import json
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent.parent / "data" / "eval_datasets"


def load(name: str) -> list:
    """Read a dataset by file name (e.g. 'research_questions_v1.jsonl').

    Blank lines are skipped; a malformed line raises with its line number so a bad
    hand-edit is caught at load, not mid-run after spending tokens.
    """
    path = DATASET_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"eval dataset not found: {path}\n"
            f"(datasets live in {DATASET_DIR}; see evals/README or ADR-0062)")
    items = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as err:
            raise ValueError(f"{name}:{i} is not valid JSON — {err}") from err
    return items
