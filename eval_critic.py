"""eval_critic — test-driven evaluation of the critic agent.

Implements the evaluation battery from the critic design discussion. Cases are
seeded with candidate labels (edit / add your own gold labels below). Abstracts are
embedded so the eval is deterministic and offline; only the critic's LLM call runs.

The two headline metrics, in tension:
  - fabrication/junk/type RECALL  (does it catch hallucinations & malformed junk?)
  - novelty PRESERVATION          (does it keep valid NOVEL links, not reject them?)
A good critic scores high on BOTH.

Run:  KG_BACKEND=hetionet python eval_critic.py
"""

# (name, record, abstract, expect_reject, tag)
CASES = [
    ("valid-grounded",
     {"subject": "CXCL8", "predicate": "associates", "object": "ulcerative colitis"},
     "In this cohort of ulcerative colitis patients, CXCL8 (IL-8) was significantly "
     "upregulated in inflamed mucosa and associated with disease activity.",
     False, "valid"),

    ("fabrication-offtopic",
     {"subject": "CXCL8", "predicate": "treats", "object": "type 2 diabetes"},
     "In ulcerative colitis, CXCL8 was upregulated in inflamed mucosa. No metabolic "
     "or diabetes outcomes were assessed in this study.",
     True, "fabrication"),

    ("novel-valid",
     {"subject": "Resolvin D5", "predicate": "inhibits", "object": "CXCL8"},
     "Resolvin D5 (RvD5) reduced CXCL8 secretion and neutrophil infiltration in an "
     "experimental colitis model, indicating a pro-resolving role.",
     False, "novel"),

    ("type-violation",
     {"subject": "abdominal pain", "predicate": "treats", "object": "CXCL8"},
     "Abdominal pain was a common presenting symptom; mucosal CXCL8 was measured.",
     True, "type"),

    ("junk-entity",
     {"subject": "CID11879209", "predicate": "associates", "object": "CCL3"},
     "Compound screening identified several hits linked to chemokine expression.",
     True, "junk"),

    ("unsupported-but-plausible",
     {"subject": "TNF", "predicate": "upregulates", "object": "CXCL8"},
     "This review discusses epithelial barrier function in IBD; it does not report a "
     "direct TNF-CXCL8 relationship.",
     True, "fabrication"),

    ("valid-drug-disease",
     {"subject": "infliximab", "predicate": "treats", "object": "Crohn's disease"},
     "Infliximab, an anti-TNF monoclonal antibody, induced clinical remission in "
     "patients with moderate-to-severe Crohn's disease in this randomized trial (n=573).",
     False, "valid"),

    ("fabrication-swap",
     {"subject": "IL6", "predicate": "causes", "object": "Alzheimer's disease"},
     "Elevated IL6 was associated with disease activity in rheumatoid arthritis; "
     "tocilizumab reduced IL6 signaling. No neurological outcomes were assessed.",
     True, "fabrication"),

    ("novel-valid-2",
     {"subject": "ANXA2", "predicate": "inhibits", "object": "ferroptosis"},
     "Annexin A2 (ANXA2) knockdown increased lipid peroxidation and ferroptotic cell "
     "death; ANXA2 overexpression inhibited ferroptosis in intestinal epithelial cells.",
     False, "novel"),

    ("junk-accession",
     {"subject": "GSE12345", "predicate": "associates", "object": "ulcerative colitis"},
     "Transcriptomic profiling (dataset GSE12345) of colonic biopsies revealed "
     "differentially expressed chemokines in ulcerative colitis.",
     True, "junk"),

    ("type-violation-2",
     {"subject": "CXCL8", "predicate": "treats", "object": "IL6"},
     "Both CXCL8 and IL6 were elevated in inflamed intestinal tissue.",
     True, "type"),

    ("tautology",
     {"subject": "ulcerative colitis", "predicate": "associates", "object": "ulcerative colitis"},
     "Ulcerative colitis is a chronic inflammatory bowel disease of the colon.",
     True, "junk"),
]


def run(votes: int = 1):
    import critic
    rows = []
    for name, rec, abstract, expect_reject, tag in CASES:
        rec = {**rec, "evidence": [{"source": "PMID:x"}]}
        v = critic.criticize(rec, abstract=abstract, votes=votes)
        pred_reject = v.get("verdict") == "reject"
        ok = pred_reject == expect_reject
        rows.append((name, tag, v.get("verdict"), expect_reject, ok))
        print(f"[{'OK' if ok else 'XX'}] {name:26} verdict={str(v.get('verdict')):9} "
              f"expect_reject={expect_reject}")

    acc = sum(r[4] for r in rows) / len(rows)
    fab = [r for r in rows if r[1] in ("fabrication", "junk", "type")]
    fab_recall = sum(1 for r in fab if r[2] == "reject") / len(fab)
    nov = [r for r in rows if r[1] == "novel"]
    nov_pres = (sum(1 for r in nov if r[2] != "reject") / len(nov)) if nov else 1.0
    print(f"\n{len(CASES)} cases (votes={votes}): accuracy {acc:.2f}  |  "
          f"fabrication/junk/type recall {fab_recall:.2f}  |  novelty preserved {nov_pres:.2f}")
    return acc, fab_recall, nov_pres


def consistency(indices=(1, 3, 5), runs=3):
    """Run the critic repeatedly on the same cases and report verdict agreement."""
    import critic
    print("\n=== consistency (same case repeated) ===")
    for i in indices:
        name, rec, abstract, _, _ = CASES[i]
        rec = {**rec, "evidence": [{"source": "PMID:x"}]}
        verdicts = [critic.criticize(rec, abstract=abstract).get("verdict")
                    for _ in range(runs)]
        agree = max(verdicts.count(v) for v in set(verdicts)) / len(verdicts)
        print(f"  {name:26} {verdicts}  agreement {agree:.2f}")


if __name__ == "__main__":
    run()
    consistency()
