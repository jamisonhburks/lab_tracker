"""literature_grounding — fidelity of the model to supplied abstracts (the hallucination test).

Given a hypothesis and a handful of real abstracts, does the model's assessment accurately
represent what those abstracts say, or does it hallucinate support and over-interpret? This is
the eval that most directly tests the failure mode a biomedical assistant must not have.

The task is deliberately the model's NATURAL free-text answer (not a constrained form, which
would itself suppress hallucination and bias the measurement). A second pass extracts the claims
it made and the abstracts it cited; each cited claim is then verified against that abstract —
the same source-supported check critic.py runs on extracted associations, applied here to
summarization. Planted distractor claims (true-sounding but unsupported) catch false endorsement.

Metrics (per item, aggregated with bootstrap 95% CIs):
  precision             : fraction of the model's CITED claims the cited abstract actually supports
  recall                : fraction of ground-truth supported claims the model surfaced
  hallucination_rate    : fraction of cited claims the cited abstract does NOT support (1 - precision)
  distractor_endorsement: fraction of planted distractors the model wrongly asserts as supported

Dataset (data/eval_datasets/literature_grounding_v1.jsonl) is seeded from REAL papers — the lab's
own publications and their references, where the ground truth is known first-hand (see ADR-0062).
Abstract indices are 1-based. The dataset is NOT shipped with placeholder text: a grounding
benchmark built on invented abstracts measures nothing.
"""

import os

from pydantic import BaseModel

import llm
from evals import _dataset, _scorer

DATASET = "literature_grounding_v1.jsonl"

SUBJECT_PROMPT = """You are assessing a hypothesis strictly against the evidence in the \
abstracts below. Use ONLY these abstracts — do not rely on outside knowledge.

For each point you make, cite the abstract number(s) [1..{n}] it comes from, like [1] or [2,3].
State what the abstracts SUPPORT, what they REFUTE, and what they do not address.

HYPOTHESIS: {hypothesis}

{abstracts}
"""

# --- claim extraction from the model's free-text answer -----------------------------------
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "cites": {"type": "array", "items": {"type": "integer"}},
                    "stance": {"type": "string"},   # supports | refutes | unclear
                },
                "required": ["text", "cites"],
            },
        },
    },
    "required": ["claims"],
}


class _Claim(BaseModel):
    text: str
    cites: list[int] = []
    stance: str = ""


class _Claims(BaseModel):
    claims: list[_Claim] = []


EXTRACT_PROMPT = """Extract the distinct factual claims the TEXT makes about the hypothesis, and \
the abstract number(s) each claim cites. Do not add claims the text does not make; do not drop \
citations it gives. Return JSON: claims = [{{text, cites:[ints], stance: supports|refutes|unclear}}].

TEXT:
{response}
"""

# --- single-field 0/1 judges, reused via _scorer.judge (median over votes) -----------------
VERIFY_SCHEMA = {"type": "object",
                 "properties": {"supported": {"type": "integer"}, "reason": {"type": "string"}},
                 "required": ["supported"]}
MATCH_SCHEMA = {"type": "object", "properties": {"match": {"type": "integer"}},
                "required": ["match"]}
DISTRACTOR_SCHEMA = {"type": "object",
                     "properties": {"endorsed": {"type": "integer"}, "reason": {"type": "string"}},
                     "required": ["endorsed"]}


class _Verify(BaseModel):
    supported: int = 0
    reason: str = ""


class _Match(BaseModel):
    match: int = 0


class _Distractor(BaseModel):
    endorsed: int = 0
    reason: str = ""


def _judge01(prompt, schema, model_cls, field, backend, votes):
    """A 0/1 judge: reuse the multi-vote median machinery, then threshold the median."""
    r = _scorer.judge(prompt, schema, model_cls, numeric_fields=[field],
                      backend=backend, votes=votes)
    return 1 if int(r.get(field, 0)) >= 1 else 0


def _verify(claim: str, abstract_text: str, backend, votes) -> int:
    prompt = ("Does the ABSTRACT below explicitly support the CLAIM? Answer strictly on the "
              "abstract's text; if it does not state it, the answer is 0. Return JSON: "
              f"supported (1 or 0), reason.\n\nCLAIM: {claim}\n\nABSTRACT:\n{abstract_text}")
    return _judge01(prompt, VERIFY_SCHEMA, _Verify, "supported", backend, votes)


def _match(extracted: str, gt_claim: str, backend, votes) -> int:
    prompt = ("Do these two statements assert the SAME finding (same relationship, same "
              "direction)? Minor wording differences are fine. Return JSON: match (1 or 0).\n\n"
              f"A: {extracted}\n\nB: {gt_claim}")
    return _judge01(prompt, MATCH_SCHEMA, _Match, "match", backend, votes)


def _endorses(response: str, distractor: str, backend, votes) -> int:
    prompt = ("Does the ASSESSMENT claim the abstracts SUPPORT the following statement? Answer 1 "
              "only if the assessment asserts the abstracts back it up (not if it says they do "
              "not, or is silent). Return JSON: endorsed (1 or 0), reason.\n\n"
              f"STATEMENT: {distractor}\n\nASSESSMENT:\n{response}")
    return _judge01(prompt, DISTRACTOR_SCHEMA, _Distractor, "endorsed", backend, votes)


def score_item(item: dict, backend=None, judge_backend=None, judge_votes=3) -> dict:
    abstracts = item["abstracts"]
    numbered = "\n\n".join(f"[{i}] {a}" for i, a in enumerate(abstracts, 1))
    resp = llm.chat([{"role": "user", "content": SUBJECT_PROMPT.format(
        n=len(abstracts), hypothesis=item["hypothesis"], abstracts=numbered)}],
        backend=backend).text

    try:
        extracted = llm.parse([{"role": "user", "content": EXTRACT_PROMPT.format(response=resp)}],
                              EXTRACT_SCHEMA, _Claims, backend=judge_backend).model_dump()["claims"]
    except Exception:
        extracted = []

    cited = [c for c in extracted if c.get("cites")]
    verdicts = []
    for c in cited:
        idxs = [i for i in c["cites"] if 1 <= i <= len(abstracts)]
        if not idxs:
            verdicts.append(0)          # cited an abstract that does not exist → unsupported
            continue
        text = "\n\n".join(abstracts[i - 1] for i in idxs)
        verdicts.append(_verify(c["text"], text, judge_backend, judge_votes))

    gt = item.get("ground_truth", [])
    recalled = [1 if any(_match(c["text"], g["claim"], judge_backend, judge_votes)
                         for c in extracted) else 0 for g in gt]
    distractors = item.get("distractor_claims", [])
    endorsed = [_endorses(resp, d, judge_backend, judge_votes) for d in distractors]

    precision = _scorer.mean(verdicts) if cited else None
    return {
        "id": item.get("id"),
        "n_claims": len(extracted), "n_cited": len(cited),
        "precision": round(precision, 3) if precision is not None else None,
        "hallucination_rate": round(1 - precision, 3) if precision is not None else None,
        "recall": round(_scorer.mean(recalled), 3) if gt else None,
        "distractor_endorsement": round(_scorer.mean(endorsed), 3) if distractors else None,
        "response": resp, "claims": extracted,
    }


def run(backend: str = None, dataset: str = DATASET, judge_backend: str = None,
        judge_votes: int = None, limit: int = None) -> dict:
    judge_backend = judge_backend or os.environ.get("EVAL_JUDGE_BACKEND") or backend
    judge_votes = judge_votes if judge_votes is not None else int(os.environ.get("EVAL_JUDGE_VOTES", "3"))
    limit = limit if limit is not None else (int(os.environ["EVAL_LIMIT"])
            if os.environ.get("EVAL_LIMIT") else None)
    items = _dataset.load(dataset)
    if limit:
        items = items[:limit]
    recs = [score_item(it, backend=backend, judge_backend=judge_backend, judge_votes=judge_votes)
            for it in items]

    def mci(field):
        vals = [r[field] for r in recs if r.get(field) is not None]
        return {"mean": round(_scorer.mean(vals), 3), "ci": _scorer.bootstrap_ci(vals), "n": len(vals)}

    metrics = {"n": len(recs), "precision": mci("precision"), "recall": mci("recall"),
               "hallucination_rate": mci("hallucination_rate"),
               "distractor_endorsement": mci("distractor_endorsement")}
    return {
        "benchmark": "literature_grounding",
        "backend": (backend or llm.BACKEND).lower(),
        "judge_backend": judge_backend, "judge_votes": judge_votes, "dataset": dataset,
        "metrics": metrics,
        "summary": f"precision={metrics['precision']['mean']} recall={metrics['recall']['mean']} "
                   f"hallucination={metrics['hallucination_rate']['mean']} "
                   f"distractor_endorsement={metrics['distractor_endorsement']['mean']} (n={metrics['n']})",
        "predictions": recs,
    }
