"""eval_critic — test-driven evaluation of the critic agent.

Implements the evaluation battery from the critic design discussion. Cases are
seeded with candidate labels (edit / add your own gold labels below). Abstracts are
embedded so the eval is deterministic and offline; only the critic's LLM call runs.

The two headline metrics, in tension:
  - fabrication/junk/type RECALL  (does it catch hallucinations & malformed junk?)
  - novelty PRESERVATION          (does it keep valid NOVEL links, not reject them?)
A good critic scores high on BOTH. Run:  KG_BACKEND=hetionet python eval_critic.py
"""

# (name, record, abstract, expect_reject, tag)
CASES = [
    ("valid-grounded",
     {"subject": "CXCL8", "predicate": "associates", "object": "ulcerative colitis",
      "evidence": [{"source": "PMID:x"}]},
     "In this cohort of ulcerative colitis patients, CXCL8 (IL-8) was significantly "
     "upregulated in inflamed mucosa and associated with disease activity.",
     False, "valid"),

    ("fabrication-offtopic",
     {"subject": "CXCL8", "predicate": "treats", "object": "type 2 diabetes",
      "evidence": [{"source": "PMID:x"}]},
     "In ulcerative colitis, CXCL8 was upregulated in inflamed mucosa. No metabolic "
     "or diabetes outcomes were assessed in this study.",
     True, "fabrication"),

    ("novel-valid",
     {"subject": "Resolvin D5", "predicate": "inhibits", "object": "CXCL8",
      "evidence": [{"source": "PMID:x"}]},
     "Resolvin D5 (RvD5) reduced CXCL8 secretion and neutrophil infiltration in an "
     "experimental colitis model, indicating a pro-resolving role.",
     False, "novel"),

    ("type-violation",
     {"subject": "abdominal pain", "predicate": "treats", "object": "CXCL8",
      "evidence": [{"source": "PMID:x"}]},
     "Abdominal pain was a common presenting symptom; mucosal CXCL8 was measured.",
     True, "type"),

    ("junk-entity",
     {"subject": "CID11879209", "predicate": "associates", "object": "CCL3",
      "evidence": [{"source": "PMID:x"}]},
     "Compound screening identified several hits linked to chemokine expression.",
     True, "junk"),

    ("unsupported-but-plausible",
     {"subject": "TNF", "predicate": "upregulates", "object": "CXCL8",
      "evidence": [{"source": "PMID:x"}]},
     "This review discusses epithelial barrier function in IBD; it does not report a "
     "direct TNF-CXCL8 relationship.",
     True, "fabrication"),
]


def run():
    import critic
    rows = []
    for name, rec, abstract, expect_reject, tag in CASES:
        v = critic.criticize(rec, abstract=abstract)
        pred_reject = v.get("verdict") == "reject"
        ok = pred_reject == expect_reject
        rows.append((name, tag, v.get("verdict"), expect_reject, ok))
        mark = "OK" if ok else "XX"
        print(f"[{mark}] {name:26} verdict={str(v.get('verdict')):9} "
              f"expect_reject={expect_reject}  reason={str(v.get('reason'))[:56]}")

    acc = sum(r[4] for r in rows) / len(rows)
    fab = [r for r in rows if r[1] in ("fabrication", "junk", "type")]
    fab_recall = sum(1 for r in fab if r[2] == "reject") / len(fab)
    nov = [r for r in rows if r[1] == "novel"]
    nov_pres = (sum(1 for r in nov if r[2] != "reject") / len(nov)) if nov else 1.0
    print(f"\naccuracy {acc:.2f}  |  fabrication/junk/type recall {fab_recall:.2f}  "
          f"|  novelty preserved {nov_pres:.2f}")
    return acc, fab_recall, nov_pres


if __name__ == "__main__":
    run()
