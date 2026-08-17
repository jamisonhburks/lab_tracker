#!/usr/bin/env python3
"""H003 — Substrate lift benchmark (Hetionet drug-repurposing, four arms).

Tests the load-bearing claim: does grounding a small local model in the substrate (indirect KG
mechanism paths + a grounding grade) make its confidence HONEST and its mechanisms TRUTHFUL —
matching/beating a bare frontier model on the axes that matter (calibration, not memorized recall)?

Design (2x2): {qwen3:14b local, frontier Claude} x {bare, +substrate}. +substrate AUGMENTS the
model (keeps its knowledge, grounded+calibrated by the KG), it does not restrict it. Task:
Compound-treats-Disease prediction over Hetionet with held-out test edges REMOVED from the graph
the substrate sees, so it reasons over indirect paths (the Rephetio setup).

Negatives are mostly HARD (plausible-but-false: the compound binds a gene associated with the
disease but does not treat it) — the regime where a bare model confidently invents a mechanism and
grounding should restrain it. Metrics per arm:
  precision@k, AUROC, AUPRC          — ranking
  ECE                                — calibration (the substrate's core claim)
  confidently_wrong_rate             — high-confidence false alarms / missed positives (headline)
  hallucination_rate                 — cites a mechanism not on any real KG path between the pair
plus a per-grounding-grade breakdown showing confidence tracks the grade.

The judge is pluggable (model-agnosticism in action): ollama | anthropic (SDK, needs a key) |
frontier→external (prompts to a queue, answers read back — filled by a subagent, batch job, or human).

Run:
  KG_BACKEND=hetionet python experiments/H003_substrate_lift/run.py --smoke
  python experiments/H003_substrate_lift/run.py --smoke --arms c,d      # after the queue is filled
  python experiments/H003_substrate_lift/run.py                         # full: 3 seeds, all arms
"""
import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
ROOT = EXP.parents[1]
sys.path.insert(0, str(ROOT))

import yaml                       # noqa: E402
import polars as pl               # noqa: E402
import kg_memory                  # noqa: E402
import llm                        # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

try:
    from src.utils.log_run_metadata import log_run_metadata
except Exception:                 # pragma: no cover
    log_run_metadata = None

S, P, O = kg_memory.EDGE_SUBJ, kg_memory.EDGE_PRED, kg_memory.EDGE_OBJ


class BenchAnswer(BaseModel):
    treats: bool
    confidence: float = Field(ge=0.0, le=1.0, description="probability the drug treats the disease")
    mechanism: str = Field(default="", description="the supporting intermediary/mechanism, or 'none'")


# --------------------------------------------------------------------------- #
# Config + logging                                                             #
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    return yaml.safe_load((EXP / "config.yaml").read_text(encoding="utf-8"))


def setup_logger(log_file: str) -> logging.Logger:
    p = ROOT / log_file
    p.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("H003")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    for h in (logging.FileHandler(p, mode="w", encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logger.addHandler(h)
    return logger


# --------------------------------------------------------------------------- #
# Knowledge graph + dataset                                                   #
# --------------------------------------------------------------------------- #
def load_kg(cfg) -> dict:
    os.environ["KG_BACKEND"] = cfg["kg_backend"]
    kg_memory.load_hetionet()
    return {n[kg_memory.NODE_ID]: (n[kg_memory.NODE_NAME], n[kg_memory.NODE_CAT])
            for n in kg_memory._G["nodes"].to_dicts()}


def ctd_positives() -> list:
    e = kg_memory._G["edges"]
    ctd = e.filter((pl.col(P) == "treats") & pl.col(S).str.starts_with("Compound:")
                   & pl.col(O).str.starts_with("Disease:"))
    return [(r[S], r[O]) for r in ctd.to_dicts()]


def hard_neg_maps():
    """gene->[compounds that bind it], disease->[genes associated with it]. A pair drawn as
    (a binder of a gene associated with the disease) has a real Cb G-DaG path but no treats-edge —
    a plausible-but-false HARD negative."""
    e = kg_memory._G["edges"]
    binds = e.filter((pl.col(P) == "binds") & pl.col(S).str.starts_with("Compound:")
                     & pl.col(O).str.starts_with("Gene:"))
    assoc = e.filter((pl.col(P) == "associates") & pl.col(S).str.starts_with("Disease:")
                     & pl.col(O).str.starts_with("Gene:"))
    g2c, d2g = {}, {}
    for r in binds.select([S, O]).iter_rows():
        g2c.setdefault(r[1], []).append(r[0])
    for r in assoc.select([S, O]).iter_rows():
        d2g.setdefault(r[0], []).append(r[1])
    return g2c, d2g


def sample_hard(n, rng, pos_set, g2c, d2g):
    dz = [d for d, gs in d2g.items() if gs]
    out, tries = set(), 0
    while len(out) < n and tries < n * 400 and dz:
        tries += 1
        d = rng.choice(dz)
        g = rng.choice(d2g[d])
        if g in g2c:
            c = rng.choice(g2c[g])
            if (c, d) not in pos_set:
                out.add((c, d))
    return list(out)


def build_dataset(positives_all, comp_ids, dis_ids, g2c, d2g, n_pos, n_neg, hard_frac, seed):
    rng = random.Random(seed)
    pos_set = set(positives_all)
    pos = rng.sample(positives_all, min(n_pos, len(positives_all)))
    n_hard = int(round(n_neg * hard_frac))
    hard = sample_hard(n_hard, rng, pos_set, g2c, d2g)
    easy, tries = [], 0
    while len(easy) < (n_neg - len(hard)) and tries < n_neg * 100:
        c, d = rng.choice(comp_ids), rng.choice(dis_ids)
        tries += 1
        if (c, d) not in pos_set:
            easy.append((c, d))
    pairs = ([(c, d, 1, "pos") for c, d in pos]
             + [(c, d, 0, "hard") for c, d in hard]
             + [(c, d, 0, "easy") for c, d in easy])
    rng.shuffle(pairs)
    return pos, pairs


def restore_edges(full):
    kg_memory._G["edges"] = full
    kg_memory._reset()


def remove_ctd_edges(held_out):
    keys = [f"{c}|{d}" for c, d in held_out]
    e = kg_memory._G["edges"].with_columns((pl.col(S) + "|" + pl.col(O)).alias("_k"))
    e = e.filter(~((pl.col(P) == "treats") & pl.col("_k").is_in(keys))).drop("_k")
    kg_memory._G["edges"] = e
    kg_memory._reset()


# --------------------------------------------------------------------------- #
# Path grading / formatting (one BFS reused for grade + entities + evidence)   #
# --------------------------------------------------------------------------- #
def _grade(a_id, c_id, paths) -> str:
    if a_id is None or c_id is None:
        return "off_graph"
    if not paths:
        return "novel_unverified"
    for p in paths:                    # shortest-first (enumerate_paths sorts by length)
        maj = sum(kg_memory._trustworthy(src) for (_, _, _, src, _) in p) * 2 > len(p)
        if len(p) <= 2 and maj:
            return "grounded"
    return "weakly_grounded"


def _path_entities(paths) -> set:
    ents = set()
    for p in paths:
        for frm, _, _, _, to in p:
            ents.add(kg_memory._label(frm))
            ents.add(kg_memory._label(to))
    return ents


def _format_paths(a_id, c_id, paths, truncated, label=None) -> str:
    lbl = label or kg_memory._label
    if a_id is None or c_id is None:
        return "(one or both entities are absent from the knowledge graph.)"
    if not paths:
        return "No indirect mechanistic path was found in the knowledge graph."
    out = ["Indirect mechanistic paths (the direct treats-link is intentionally withheld):"]
    for p in paths[:6]:
        chain, srcs = lbl(p[0][0]), []
        for _, pred, arrow, src, to in p:
            chain += f"  —{pred}{'→' if arrow == '->' else '←'}  {lbl(to)}"
            srcs.append(src)
        out.append(f"  • {chain}\n      via: {', '.join(dict.fromkeys(srcs))}")
    if truncated:
        out.append("  (search truncated — more paths may exist)")
    return "\n".join(out)


def make_aliases(drug_id, disease_id, paths, meta, enabled):
    """Per-pair opaque IDs: keep the TYPE (Compound/Gene/Disease), hide the identity, so the model
    can't use memorized public facts and must reason over the graph. Relations stay real. Returns
    (label_fn, drug_label, disease_label, shown_entities)."""
    if not enabled:
        lbl = kg_memory._label
        return lbl, lbl(drug_id), lbl(disease_id), set()
    order, seen = [drug_id, disease_id], {drug_id, disease_id}
    for p in paths:
        for frm, _, _, _, to in p:
            for nid in (frm, to):
                if nid not in seen:
                    seen.add(nid)
                    order.append(nid)
    counts, alias = {}, {}
    for nid in order:
        cat = (meta.get(nid) or ("", "Node"))[1] or "Node"
        counts[cat] = counts.get(cat, 0) + 1
        alias[nid] = f"{cat}_{counts[cat]}"
    return (lambda nid: alias.get(nid, "Node_?")), alias[drug_id], alias[disease_id], set(alias.values())


# --------------------------------------------------------------------------- #
# Prompts                                                                       #
# --------------------------------------------------------------------------- #
def bare_prompt(drug, disease) -> str:
    return (f"You are assessing a potential drug repurposing.\n"
            f"Drug: {drug}\nDisease: {disease}\n\n"
            f"Does this drug TREAT this disease (an established or mechanistically plausible "
            f"indication)?\nReply as JSON: "
            f'{{"treats": <bool>, "confidence": <0..1 it treats>, '
            f'"mechanism": "<the single most likely molecular intermediary (gene/protein/pathway), '
            f'or \'none\'>"}}')


def substrate_prompt(drug, disease, evidence, grade) -> str:
    # AUGMENT (not restrict): keep your knowledge, let the KG ground + calibrate it.
    return (f"You are assessing a potential drug repurposing. Use BOTH your own pharmacology "
            f"knowledge AND a biomedical knowledge graph that grounds it.\n"
            f"Drug: {drug}\nDisease: {disease}\n\n"
            f"Knowledge-graph evidence:\n{evidence}\n\nKG grounding grade for this pair: {grade}\n\n"
            f"Judge whether the drug TREATS the disease using what you know, GROUNDED and "
            f"CALIBRATED by this evidence: when the graph gives strong, direct mechanistic support "
            f"be more confident; when it gives only weak, indirect, or no support, LOWER your "
            f"confidence accordingly even if you hold a prior. Prefer a mechanism corroborated by "
            f"the evidence; if you cite one from your own knowledge, keep confidence modest unless "
            f"the graph supports it.\nReply as JSON: "
            f'{{"treats": <bool>, "confidence": <0..1>, "mechanism": "<the supporting intermediary, '
            f'ideally one named in the evidence>"}}')


# --------------------------------------------------------------------------- #
# Judges + hallucination check                                                #
# --------------------------------------------------------------------------- #
def judge_model(prompt, backend, model, logger):
    try:
        ans = llm.parse([{"role": "user", "content": prompt}],
                        BenchAnswer.model_json_schema(), BenchAnswer, backend=backend, model=model)
        return {"treats": bool(ans.treats), "confidence": float(ans.confidence),
                "mechanism": ans.mechanism, "ok": True}
    except Exception as err:
        logger.info(f"    [judge error {backend}/{model}: {type(err).__name__}: {str(err)[:80]}]")
        return {"treats": False, "confidence": 0.0, "mechanism": "[error]", "ok": False}


def load_answers(path) -> dict:
    p = ROOT / path
    out = {}
    if p.exists():
        for line in p.open(encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                out[(r["arm"], r["pair_id"])] = r
    return out


def mech_hallucinated(treats, mechanism, oracle_entities) -> bool:
    """Claimed a treatment mechanism the KG can't corroborate: predicted treats with a specific
    intermediary that is NOT on any real path between the pair in the full (oracle) graph."""
    m = (mechanism or "").strip().lower()
    if not treats or m in ("", "none", "n/a", "[error]"):
        return False
    if not oracle_entities:            # no supporting path at all → any named mechanism is invented
        return True
    return not any(e.lower() in m for e in oracle_entities if len(e) > 2)


# --------------------------------------------------------------------------- #
# Metrics                                                                       #
# --------------------------------------------------------------------------- #
def _ece(confs, labels, nbins=10):
    if not confs:
        return 0.0
    n, tot = len(confs), 0.0
    for i in range(nbins):
        lo, hi = i / nbins, (i + 1) / nbins
        idx = [j for j, c in enumerate(confs) if (lo <= c < hi) or (hi == 1.0 and c == 1.0)]
        if idx:
            tot += (len(idx) / n) * abs(sum(confs[j] for j in idx) / len(idx)
                                        - sum(labels[j] for j in idx) / len(idx))
    return tot


def _precision_at_k(confs, labels, k):
    order = sorted(range(len(confs)), key=lambda j: -confs[j])[:min(k, len(confs))]
    return (sum(labels[j] for j in order) / len(order)) if order else 0.0


def compute_metrics(rows, k, conf_high):
    ok = [r for r in rows if r["ok"]]
    if not ok:
        return None
    confs = [r["confidence"] for r in ok]
    labels = [r["label"] for r in ok]
    preds = [1 if r["treats"] else 0 for r in ok]
    pos_pred = [r for r in ok if r["treats"]]
    lo = 1 - conf_high
    conf_wrong = sum(1 for r in ok if (r["confidence"] >= conf_high and r["label"] == 0)
                     or (r["confidence"] <= lo and r["label"] == 1))
    m = {"n": len(ok),
         "precision_at_k": _precision_at_k(confs, labels, k),
         "accuracy": sum(1 for p, l in zip(preds, labels) if p == l) / len(ok),
         "ece": _ece(confs, labels),
         "confidently_wrong_rate": conf_wrong / len(ok),
         "hallucination_rate": (sum(1 for r in pos_pred if r["hallucinated"]) / len(pos_pred))
                               if pos_pred else 0.0}
    try:
        from sklearn.metrics import roc_auc_score, average_precision_score
        if len(set(labels)) == 2:
            m["auroc"] = float(roc_auc_score(labels, confs))
            m["auprc"] = float(average_precision_score(labels, confs))
    except Exception:
        pass
    return m


def _mean_sd(vals):
    if not vals:
        return (float("nan"), float("nan"))
    mean = sum(vals) / len(vals)
    return (mean, (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5)


# --------------------------------------------------------------------------- #
# Main                                                                          #
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--arms", default="")
    ap.add_argument("--seeds", default="")
    args = ap.parse_args()

    cfg = load_config()
    logger = setup_logger(cfg["log_file"])
    ds = cfg["smoke"] if args.smoke else cfg["dataset"]
    seeds = cfg["smoke"]["seeds"] if args.smoke else cfg["random_seeds"]
    if args.seeds:
        seeds = [int(s) for s in args.seeds.split(",")]
    n_pos, n_neg, hard_frac = ds["n_positives"], ds["n_negatives"], ds["hard_negative_frac"]
    arm_ids = [a.strip() for a in args.arms.split(",") if a.strip()] or list(cfg["arms"].keys())
    k, max_len, conf_high = cfg["precision_k"], cfg["max_path_len"], cfg["conf_high"]
    anonymize = bool(cfg.get("anonymize", False))
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if log_run_metadata:
        log_run_metadata(logger, seeds, "start")
    logger.info(f"H003 {'SMOKE ' if args.smoke else ''}| arms={arm_ids} seeds={seeds} | n_pos={n_pos} "
                f"n_neg={n_neg} (hard {hard_frac:.0%}) | anonymize={anonymize} | "
                f"frontier={'anthropic(SDK)' if has_key else 'external(cache)'}")

    meta = load_kg(cfg)
    full_edges = kg_memory._G["edges"].clone()
    positives_all = ctd_positives()
    comp_ids = [i for i, (_, c) in meta.items() if c == "Compound"]
    dis_ids = [i for i, (_, c) in meta.items() if c == "Disease"]
    g2c, d2g = hard_neg_maps()
    logger.info(f"KG: {len(positives_all)} CtD edges, {len(comp_ids)} compounds, {len(dis_ids)} "
                f"diseases, {len(d2g)} diseases with associated genes (hard-negative pool).")

    answers = load_answers(cfg["frontier_answers"])
    queue_lines, rows, pending = [], [], set()

    for seed in seeds:
        restore_edges(full_edges)
        held_out, pairs = build_dataset(positives_all, comp_ids, dis_ids, g2c, d2g,
                                        n_pos, n_neg, hard_frac, seed)
        n_hard = sum(1 for *_, t in pairs if t == "hard")
        logger.info(f"[seed {seed}] {len(pairs)} pairs: {len(held_out)} pos / {n_hard} hard-neg / "
                    f"{len(pairs)-len(held_out)-n_hard} easy-neg")

        # substrate evidence (REDUCED graph, anti-leakage) + per-pair anonymization — one BFS/pair.
        # The grade the model SAW (reduced graph) is what it calibrates against, so it drives the
        # per-grade breakdown; there's no separate full-graph oracle pass.
        remove_ctd_edges(held_out)
        evidence = {}
        for c, d, *_ in pairs:
            a, cc, ps, tr = kg_memory.enumerate_paths(meta[c][0], meta[d][0], max_len=max_len)
            lbl, drug_lab, dis_lab, shown = make_aliases(a or c, cc or d, ps, meta, anonymize)
            evidence[(c, d)] = {"text": _format_paths(a, cc, ps, tr, label=lbl),
                                "grade": _grade(a, cc, ps), "drug": drug_lab, "dis": dis_lab,
                                "shown": shown}

        for aid in arm_ids:
            arm = cfg["arms"][aid]
            backend = arm["backend"]
            live = backend in ("ollama", "anthropic") or (backend == "frontier" and has_key)
            rb = "anthropic" if backend == "frontier" else backend
            logger.info(f"[seed {seed}] arm {aid} ({arm['label']}) — {'live '+rb if live else 'external cache'}")
            for c, d, label, ntype in pairs:
                pid = f"{seed}|{c}|{d}"
                ed = evidence[(c, d)]
                if arm["substrate"]:
                    prompt = substrate_prompt(ed["drug"], ed["dis"], ed["text"], ed["grade"])
                    seen = ed["shown"]                       # entities the model was actually shown
                else:
                    prompt = bare_prompt(ed["drug"], ed["dis"])
                    seen = {ed["drug"], ed["dis"]}           # bare sees only the two opaque IDs
                if live:
                    ans = judge_model(prompt, rb, arm["model"], logger)
                else:
                    queue_lines.append({"pair_id": pid, "arm": aid, "question": prompt})
                    cached = answers.get((aid, pid))
                    if not cached:
                        pending.add(aid)
                        continue
                    ans = {"treats": bool(cached["treats"]), "confidence": float(cached["confidence"]),
                           "mechanism": cached.get("mechanism", ""), "ok": True}
                rows.append({"seed": seed, "arm": aid, "pair_id": pid, "label": label, "neg_type": ntype,
                             "oracle_grade": ed["grade"],
                             "hallucinated": mech_hallucinated(ans["treats"], ans["mechanism"], seen),
                             **ans})

    if queue_lines:
        qp = ROOT / cfg["frontier_queue"]
        qp.parent.mkdir(parents=True, exist_ok=True)
        qp.write_text("".join(json.dumps(q) + "\n" for q in queue_lines), encoding="utf-8")
        logger.info(f"Wrote {len(queue_lines)} frontier prompt(s) to {cfg['frontier_queue']}")

    # ---- write per-pair + metrics (MERGE with prior arms so local/frontier passes compose) ----
    # Each pass rewrites results only for the arms it ran; rows for arms NOT in this pass are
    # carried over from the existing pairs.jsonl. This lets the slow local arms (a,b) and the
    # externally-judged frontier arms (c,d) be produced in separate passes without clobbering.
    results_dir = ROOT / cfg["results_dir"]
    results_dir.mkdir(parents=True, exist_ok=True)
    prior_path = results_dir / "pairs.jsonl"
    prior_rows = []
    if prior_path.exists():
        for line in prior_path.open(encoding="utf-8"):
            if line.strip():
                pr = json.loads(line)
                if pr.get("arm") not in arm_ids:      # keep arms NOT recomputed this pass
                    prior_rows.append(pr)
    merged_rows = prior_rows + rows
    all_arms = [a for a in cfg["arms"].keys() if any(r["arm"] == a for r in merged_rows)]
    all_seeds = sorted({r["seed"] for r in merged_rows})
    carried = sorted({r["arm"] for r in prior_rows})
    if carried:
        logger.info(f"Merged with prior results for arm(s) {carried} (not re-run this pass).")
    prior_path.write_text("".join(json.dumps(r) + "\n" for r in merged_rows), encoding="utf-8")

    metric_keys = ["precision_at_k", "auroc", "auprc", "accuracy", "ece",
                   "confidently_wrong_rate", "hallucination_rate", "n"]
    per = {(aid, s): compute_metrics([r for r in merged_rows if r["arm"] == aid and r["seed"] == s], k, conf_high)
           for aid in all_arms for s in all_seeds}
    per = {key: v for key, v in per.items() if v}

    long_rows = [["arm", "label", "seed", "metric", "value"]]
    summary = [["arm", "label", "metric", "mean", "sd", "n_seeds"]]
    for aid in all_arms:
        label = cfg["arms"][aid]["label"]
        present = [s for s in all_seeds if (aid, s) in per]
        for mk in metric_keys:
            vals = [per[(aid, s)][mk] for s in present if mk in per[(aid, s)]]
            for s in present:
                if mk in per[(aid, s)]:
                    long_rows.append([aid, label, s, mk, per[(aid, s)][mk]])
            if vals:
                mean, sd = _mean_sd(vals)
                summary.append([aid, label, mk, round(mean, 4), round(sd, 4), len(vals)])

    # per-grounding-grade breakdown: does confidence track the grade?
    grade_rows = [["arm", "grade", "n", "mean_conf", "accuracy"]]
    for aid in all_arms:
        for g in ("grounded", "weakly_grounded", "novel_unverified", "off_graph"):
            sub = [r for r in merged_rows if r["arm"] == aid and r["oracle_grade"] == g and r["ok"]]
            if sub:
                grade_rows.append([aid, g, len(sub),
                                   round(sum(r["confidence"] for r in sub) / len(sub), 3),
                                   round(sum(1 for r in sub if (1 if r["treats"] else 0) == r["label"]) / len(sub), 3)])

    def _csv(name, rows_):
        (results_dir / name).write_text("\n".join(",".join(str(x) for x in r) for r in rows_) + "\n",
                                        encoding="utf-8")
    _csv("metrics.csv", long_rows)
    _csv("metrics_summary.csv", summary)
    _csv("metrics_by_grade.csv", grade_rows)

    # ---- console summary ----
    logger.info("\n===== SUMMARY (mean over seeds) =====")
    logger.info(f"{'arm':<24}{'ECE↓':>8}{'confWrong↓':>11}{'halluc↓':>9}{'AUROC↑':>8}{'AUPRC↑':>8}{'acc↑':>7}")

    def mv(aid, mk):
        present = [s for s in all_seeds if (aid, s) in per]
        vs = [per[(aid, s)].get(mk) for s in present if per[(aid, s)].get(mk) is not None]
        return f"{sum(vs)/len(vs):.3f}" if vs else "  -"
    for aid in all_arms:
        logger.info(f"{cfg['arms'][aid]['label']:<24}{mv(aid,'ece'):>8}{mv(aid,'confidently_wrong_rate'):>11}"
                    f"{mv(aid,'hallucination_rate'):>9}{mv(aid,'auroc'):>8}{mv(aid,'auprc'):>8}{mv(aid,'accuracy'):>7}")
    for aid in sorted(pending):
        if not any(kk[0] == aid for kk in per):
            logger.info(f"{cfg['arms'][aid]['label']:<24}  PENDING — fill {cfg['frontier_answers']} then re-run")

    present = per_present(per, all_seeds)
    if "a" in present and "b" in present:
        logger.info("\n-- substrate effect on qwen3:14b (b vs a) — under anonymization, bare is blind --")
        for mk, want in [("auroc", "↑"), ("accuracy", "↑"), ("ece", "↓"), ("confidently_wrong_rate", "↓")]:
            va = _mean_sd([per[("a", s)][mk] for s in all_seeds if ("a", s) in per and mk in per[("a", s)]])[0]
            vb = _mean_sd([per[("b", s)][mk] for s in all_seeds if ("b", s) in per and mk in per[("b", s)]])[0]
            logger.info(f"   [{mk}] want {want}: {vb-va:+.3f}  (b {vb:.3f} vs a {va:.3f})")
    if "b" in present and "c" in present:   # the pitch: grounded small model vs blind frontier
        for mk in ["auroc", "accuracy"]:
            vb = _mean_sd([per[("b", s)][mk] for s in all_seeds if ("b", s) in per and mk in per[("b", s)]])[0]
            vc = _mean_sd([per[("c", s)][mk] for s in all_seeds if ("c", s) in per and mk in per[("c", s)]])[0]
            logger.info(f"   grounded-14b vs frontier-bare [{mk}]: {vb-vc:+.3f}  (b {vb:.3f} vs c {vc:.3f})")

    if len(seeds) < 3:
        logger.info("Stats (paired tests, Bonferroni+BH, effect sizes) require >=3 seeds — this run is "
                    f"{len(seeds)} seed(s). Re-run without --smoke for the pre-registered comparison.")
    if pending:
        logger.info(f"\nPENDING frontier arms {sorted(pending)}: fill {cfg['frontier_answers']} then re-run.")
    if log_run_metadata:
        log_run_metadata(logger, seeds, "end")
    logger.info("done.")


def per_present(per, seeds):
    return {aid for (aid, s) in per}


if __name__ == "__main__":
    main()
