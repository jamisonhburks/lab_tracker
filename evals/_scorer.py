"""_scorer — shared scoring machinery for the biology benchmarks.

Two things every benchmark needs and should not reimplement:

1. `judge(...)` — LLM-as-judge with multi-vote aggregation. It is the same doctrine
   the adversarial `critic.py` already uses: a single judge call is noisy, so run it
   N times and reduce (median for scores). The judge goes through `llm.parse`, so the
   result is schema-validated with a retry on malformed output — not a raw json.loads
   that crashes on a stray token.

2. Bootstrap confidence intervals (`bootstrap_ci`, `paired_delta_ci`). numpy only — no
   scipy — so the harness adds no dependency beyond what semantic memory already pulls.
   A point estimate with no interval is exactly the overclaiming this repo avoids.

Judge caveat worth stating out loud: when the judged model and the judge model are the
same family, self-preference bias is possible. Mitigations here are a rubric-anchored
prompt and multi-vote medians; a cross-family judge (or human spot-check) is the real
fix and is noted in the case study's limitations.
"""

import statistics

import numpy as np

import llm


def judge(prompt: str, schema: dict, model_cls, numeric_fields,
          backend: str = None, votes: int = 3) -> dict:
    """Score a response by asking the model to fill `model_cls` against `schema`.

    Runs `votes` times and takes the per-field median of `numeric_fields` (odd vote
    counts give a clean majority on integer rubrics); text fields are kept from the
    ballot nearest the median so the reasoning matches the reported score. Returns the
    aggregated dict plus `_ballots` (every raw score vector) for later re-analysis.
    """
    ballots = []
    for _ in range(max(1, votes)):
        try:
            ballots.append(llm.parse([{"role": "user", "content": prompt}],
                                     schema, model_cls, backend=backend).model_dump())
        except Exception as err:               # a dead judge call must not void the run
            ballots.append({f: 0 for f in numeric_fields} | {"_error": str(err)})

    agg = dict(ballots[0])
    for f in numeric_fields:
        vals = [b.get(f, 0) for b in ballots]
        agg[f] = int(round(statistics.median(vals)))
    # Representative ballot: smallest L1 distance to the median score vector, so the
    # kept free-text reasons correspond to the reported (median) scores.
    med = [agg[f] for f in numeric_fields]
    rep = min(ballots, key=lambda b: sum(abs(b.get(f, 0) - m)
                                         for f, m in zip(numeric_fields, med)))
    for k, v in rep.items():
        if k not in numeric_fields:
            agg[k] = v
    agg["_ballots"] = [{f: b.get(f) for f in numeric_fields} for b in ballots]
    return agg


def mean(xs) -> float:
    xs = list(xs)
    return float(np.mean(xs)) if xs else 0.0


def bootstrap_ci(values, n_boot: int = 2000, seed: int = 42, stat=mean) -> list:
    """Percentile bootstrap 95% CI for `stat` over `values`. Returns [lo, hi]."""
    values = [v for v in values if v is not None]
    if len(values) < 2:
        v = stat(values) if values else 0.0
        return [round(v, 3), round(v, 3)]
    rng = np.random.default_rng(seed)
    n = len(values)
    boots = [stat([values[i] for i in rng.integers(0, n, n)]) for _ in range(n_boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return [round(float(lo), 3), round(float(hi), 3)]


def paired_delta_ci(before, after, n_boot: int = 2000, seed: int = 42) -> dict:
    """Paired bootstrap on the per-item change (after - before).

    Returns the mean delta, its 95% CI, and a two-sided bootstrap p-value (twice the
    tail mass on the side of zero the delta is NOT on). Items must be aligned by index;
    pairs with a missing value on either side are dropped (reported as `n`).
    """
    pairs = [(b, a) for b, a in zip(before, after) if b is not None and a is not None]
    if len(pairs) < 2:
        return {"n": len(pairs), "delta": 0.0, "ci": [0.0, 0.0], "p_two_sided": 1.0}
    diffs = np.array([a - b for b, a in pairs], dtype=float)
    rng = np.random.default_rng(seed)
    n = len(diffs)
    boot_means = np.array([diffs[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
    lo, hi = np.percentile(boot_means, [2.5, 97.5])
    frac_le0 = float((boot_means <= 0).mean())
    p = 2 * min(frac_le0, 1 - frac_le0)
    return {"n": n, "delta": round(float(diffs.mean()), 3),
            "ci": [round(float(lo), 3), round(float(hi), 3)],
            "p_two_sided": round(p, 4)}
