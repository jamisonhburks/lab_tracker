"""hypothesis_generation — quality benchmark for the agent's KG-grounded hypotheses.

This is the eval-driven-development subject (ADR-0063). It scores what
`agent.synthesize_hypothesis` actually produces for a research question, on four
dimensions, keeping substrate-derived signals separate from judged ones:

  - grounding   (substrate, 0-2): from kg.check_connection — grounded=2, weakly=1, else 0.
                Reported as a GUARDRAIL, not a quality target: KG-constrained generation is
                grounded by construction, so the question is whether an intervention keeps it
                there, not whether it rises.
  - specificity (judge, 0-2): does it name specific molecules/pathways and how they interact?
  - testability (judge, 0-2): does it state a refutable prediction AND a concrete experiment?
  - novelty     (substrate, PubMed, descriptive): novelty.classify status. Reported as a
                DISTRIBUTION, never folded into the quality score — this repo's doctrine is
                "novelty is not correctness" (novelty.py). Off by default (network + slow);
                enable with EVAL_NOVELTY=1.

Composite quality = mean(specificity, testability) on 0-2. `run()` scores one variant;
`eval_driven_dev()` scores baseline vs the 'testable' intervention on the SAME items and
returns the paired before/after comparison that the case study reports.

Judge note: by default the judge runs on the generation backend. When those are the same
model family, self-preference bias is possible — set EVAL_JUDGE_BACKEND to a different
backend (and see the case study's limitations). Multi-vote medians (EVAL_JUDGE_VOTES,
default 3) reduce single-call variance.
"""

import os

from pydantic import BaseModel

import agent
import novelty
from evals import _dataset, _scorer

DATASET = "research_questions_v1.jsonl"

_GROUNDING_SCORE = {"grounded": 2, "weakly_grounded": 1, "novel_unverified": 0, "off_graph": 0}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "specificity": {"type": "integer"},
        "specificity_reason": {"type": "string"},
        "testability": {"type": "integer"},
        "testability_reason": {"type": "string"},
    },
    "required": ["specificity", "testability"],
}


class JudgeScores(BaseModel):
    specificity: int = 0
    specificity_reason: str = ""
    testability: int = 0
    testability_reason: str = ""


JUDGE_PROMPT = """You are a STRICT peer reviewer scoring one machine-generated biomedical \
hypothesis on two dimensions. Score only what is ACTUALLY WRITTEN — do not credit what a \
generous reader could infer.

SPECIFICITY (0-2):
  0 = vague ("immune mechanisms", "genetic factors") — no named molecules/genes/pathways.
  1 = names a specific gene/pathway/molecule but little about how it acts.
  2 = names specific molecules/genes/pathways AND how they interact mechanistically.

TESTABILITY (0-2):
  0 = cannot be tested or refuted as written.
  1 = implies an observable prediction, but no concrete experiment is given.
  2 = states a SPECIFIC refutable prediction AND a concrete experiment (design + measured \
variable + comparison) that would confirm or refute it. A prediction that merely restates \
the hypothesis does NOT count.

Return JSON: specificity (int 0-2), specificity_reason (one sentence), testability (int 0-2), \
testability_reason (one sentence).

HYPOTHESIS:
{text}
"""


def _render(h: dict) -> str:
    """Flatten a parsed hypothesis to the text the judge scores (what the model produced)."""
    parts = [f"Hypothesis: {h.get('hypothesis', '').strip()}"]
    mechs = h.get("mechanisms", [])
    if mechs:
        parts.append("Mechanisms:\n" + "\n".join(
            f"- {m.get('intermediate', '?')} [{m.get('centrality', '?')}]: "
            f"{str(m.get('rationale', '')).strip()}" for m in mechs))
    if h.get("caveats"):
        parts.append(f"Caveats: {str(h['caveats']).strip()}")
    if h.get("falsifiable_prediction"):
        parts.append(f"Falsifiable prediction: {str(h['falsifiable_prediction']).strip()}")
    if h.get("experiment"):
        parts.append(f"Experiment: {str(h['experiment']).strip()}")
    return "\n\n".join(parts)


def _novelty_status(a_name: str, c_name: str, via: str) -> str:
    try:
        return novelty.classify(a_name, c_name, via=via or "").get("status", "unknown")
    except Exception:
        return "unknown"


def score_item(item: dict, variant: str, backend: str = None, judge_backend: str = None,
               judge_votes: int = 3, use_novelty: bool = False) -> dict:
    """Generate a hypothesis for one dataset item and score it. Returns a per-item record;
    `composite`/`specificity`/`testability` are None if generation failed (dropped from
    aggregates, counted as a failure)."""
    r = agent.synthesize_hypothesis(item["entity_a"], item["entity_c"], variant=variant)
    rec = {"id": item.get("id"), "entity_a": item["entity_a"], "entity_c": item["entity_c"],
           "variant": variant, "ok": r["ok"]}
    if not r["ok"]:
        rec.update({"error": r.get("error"), "grounding": None, "grounding_score": None,
                    "specificity": None, "testability": None, "composite": None})
        return rec

    h = r["hypothesis"]
    grounding = r["grounding"]
    judged = _scorer.judge(JUDGE_PROMPT.format(text=_render(h)), JUDGE_SCHEMA, JudgeScores,
                           numeric_fields=["specificity", "testability"],
                           backend=judge_backend, votes=judge_votes)
    spec = max(0, min(2, int(judged["specificity"])))
    test = max(0, min(2, int(judged["testability"])))
    rec.update({
        "grounding": grounding,
        "grounding_score": _GROUNDING_SCORE.get(grounding, 0),
        "specificity": spec,
        "testability": test,
        "composite": (spec + test) / 2,
        "specificity_reason": judged.get("specificity_reason", ""),
        "testability_reason": judged.get("testability_reason", ""),
        "top_mechanism": r.get("top_mechanism"),
        "hypothesis_text": _render(h),
    })
    if use_novelty:
        rec["novelty_status"] = _novelty_status(r["a_name"], r["c_name"], r.get("top_mechanism"))
    return rec


def _aggregate(recs: list) -> dict:
    ok = [r for r in recs if r["ok"]]
    def mci(field):
        vals = [r[field] for r in ok if r.get(field) is not None]
        return {"mean": round(_scorer.mean(vals), 3), "ci": _scorer.bootstrap_ci(vals)}
    from collections import Counter
    metrics = {
        "n": len(recs), "n_ok": len(ok),
        "composite": mci("composite"),
        "specificity": mci("specificity"),
        "testability": mci("testability"),
        "grounding_score": mci("grounding_score"),
        "grounding_dist": dict(Counter(r["grounding"] for r in ok)),
    }
    nov = [r.get("novelty_status") for r in ok if r.get("novelty_status")]
    if nov:
        metrics["novelty_dist"] = dict(Counter(nov))
    return metrics


def _env_cfg(backend, judge_backend, judge_votes, use_novelty, limit):
    return {
        "backend": backend,
        "judge_backend": judge_backend or os.environ.get("EVAL_JUDGE_BACKEND") or backend,
        "judge_votes": judge_votes if judge_votes is not None
                       else int(os.environ.get("EVAL_JUDGE_VOTES", "3")),
        "use_novelty": use_novelty if use_novelty is not None
                       else os.environ.get("EVAL_NOVELTY", "") == "1",
        "limit": limit if limit is not None else (int(os.environ["EVAL_LIMIT"])
                 if os.environ.get("EVAL_LIMIT") else None),
    }


def run(backend: str = None, dataset: str = DATASET, variant: str = None,
        judge_backend: str = None, judge_votes: int = None,
        use_novelty: bool = None, limit: int = None) -> dict:
    """Score ONE variant over the dataset. variant defaults to EVAL_VARIANT or 'baseline'.
    This is the entry point biology_evals.py calls."""
    cfg = _env_cfg(backend, judge_backend, judge_votes, use_novelty, limit)
    variant = variant or os.environ.get("EVAL_VARIANT", "baseline")
    items = _dataset.load(dataset)
    if cfg["limit"]:
        items = items[:cfg["limit"]]
    recs = [score_item(it, variant, backend=backend, judge_backend=cfg["judge_backend"],
                        judge_votes=cfg["judge_votes"], use_novelty=cfg["use_novelty"])
            for it in items]
    metrics = _aggregate(recs)
    comp = metrics["composite"]
    return {
        "benchmark": "hypothesis_generation",
        "backend": (backend or __import__("llm").BACKEND).lower(),
        "variant": variant, "dataset": dataset,
        "judge_backend": cfg["judge_backend"], "judge_votes": cfg["judge_votes"],
        "metrics": metrics,
        "summary": f"variant={variant} composite={comp['mean']}/2.0 "
                   f"[95% CI {comp['ci'][0]}-{comp['ci'][1]}] "
                   f"(spec={metrics['specificity']['mean']}, test={metrics['testability']['mean']}, "
                   f"n_ok={metrics['n_ok']}/{metrics['n']})",
        "predictions": recs,
    }


def eval_driven_dev(backend: str = None, dataset: str = DATASET, judge_backend: str = None,
                    judge_votes: int = None, use_novelty: bool = None, limit: int = None) -> dict:
    """Score baseline vs the 'testable' intervention on the SAME items, aligned per item, and
    return the paired before/after comparison the case study reports. One generation + one
    judge call per (item, variant)."""
    cfg = _env_cfg(backend, judge_backend, judge_votes, use_novelty, limit)
    items = _dataset.load(dataset)
    if cfg["limit"]:
        items = items[:cfg["limit"]]

    base, intervention = [], []
    for it in items:
        base.append(score_item(it, "baseline", backend=backend, judge_backend=cfg["judge_backend"],
                               judge_votes=cfg["judge_votes"], use_novelty=cfg["use_novelty"]))
        intervention.append(score_item(it, "testable", backend=backend,
                            judge_backend=cfg["judge_backend"], judge_votes=cfg["judge_votes"],
                            use_novelty=cfg["use_novelty"]))

    paired = {f: _scorer.paired_delta_ci([b.get(f) for b in base],
                                         [i.get(f) for i in intervention])
              for f in ("composite", "specificity", "testability", "grounding_score")}
    return {
        "benchmark": "hypothesis_generation",
        "mode": "eval_driven_dev",
        "backend": (backend or __import__("llm").BACKEND).lower(),
        "judge_backend": cfg["judge_backend"], "judge_votes": cfg["judge_votes"],
        "dataset": dataset, "n": len(items),
        "baseline": _aggregate(base),
        "intervention": _aggregate(intervention),
        "paired_delta": paired,
        "summary": f"composite {_aggregate(base)['composite']['mean']} -> "
                   f"{_aggregate(intervention)['composite']['mean']} "
                   f"(Δ={paired['composite']['delta']}, "
                   f"95% CI {paired['composite']['ci']}, p={paired['composite']['p_two_sided']})",
        "predictions": {"baseline": base, "intervention": intervention},
    }
