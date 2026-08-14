"""ml_schema — the ML/method layer of the fused KG, built around the fact that
METHODS ARE EPISTEMICALLY DIFFERENT FROM PHENOMENA.

A biomedical association (gene -> disease) is DISCOVERED: author-independent, roughly
stationary, true/false; papers are *evidence*, not *creators*. An ML method claim
(Transformer used_for translation; RoBERTa outperforms BERT on GLUE) is a property of a
CREATED artifact: author-ATTRIBUTED, TIME-INDEXED, benchmark-relative/non-stationary, and
effective-in-context rather than true. The schema reflects that:

  - Methods carry AUTHORSHIP (first/last author, lab) and a YEAR — made by people, at a
    time, unlike genes. (Caveat: last-author-as-PI is a *biomedical* convention; ML author
    order is noisier, so last_author is captured as data, not read as "senior".)
  - Methods have LINEAGE: derived_from (parent) and superseded_by (successor).
  - Effectiveness edges are epistemically split: 'suited_to'/'trained_with'/'used_for' are
    stable methodological knowledge (higher trust); 'achieves'/'outperforms' are
    BENCHMARK-relative + time-indexed and default to LOW trust (SOTA churns) — their edge
    source is tagged 'benchmark:...' so kg_memory's grounding treats them as weak.

The bridge to the biomedical KG is DataModality + Task: a Disease `manifests_in` a
modality, a modality is `suited_to` an architecture — so one traversal crosses domains
(clinical question -> modality -> architecture -> loss -> metric -> caveat).

Emits rows in kg_memory's shape (id/name/category ; subject/predicate/object/source), so
the existing traversal/DWPC/calibration/grounding code works unchanged.
"""

from dataclasses import dataclass, field
from enum import Enum


class Episteme(str, Enum):
    PHENOMENON = "phenomenon"                     # discovered, stationary (biomedical)
    METHOD_ARTIFACT = "method_artifact"           # a created, authored thing
    METHOD_CLAIM_STABLE = "method_claim_stable"   # suited_to/trained_with/used_for (higher trust)
    METHOD_CLAIM_BENCHMARK = "method_claim_benchmark"  # achieves/outperforms (low trust, time-indexed)


# predicate -> epistemic class of the *edge*
_STABLE = {"suited_to", "trained_with", "used_for", "evaluated_by", "operates_on",
           "manifests_in", "has_caveat"}
_BENCHMARK = {"achieves", "outperforms"}
_ARTIFACT = {"derived_from", "superseded_by", "first_author", "last_author",
             "from_lab", "introduced_by"}


def classify_edge(predicate: str) -> Episteme:
    p = predicate.lower()
    if p in _BENCHMARK:
        return Episteme.METHOD_CLAIM_BENCHMARK
    if p in _ARTIFACT:
        return Episteme.METHOD_ARTIFACT
    if p in _STABLE:
        return Episteme.METHOD_CLAIM_STABLE
    return Episteme.PHENOMENON


@dataclass
class Method:
    """A created ML artifact — architecture / model / method / loss — with the
    epistemically-distinct fields phenomena don't have: authorship, lab, year, lineage."""
    name: str
    category: str = "Architecture"          # Architecture | Model | Method | Loss
    year: int | None = None
    first_author: str = ""
    last_author: str = ""                    # captured, but not "senior" in ML (see caveat)
    lab: str = ""
    intro_paper: str = ""                    # arXiv id / DOI — the artifact's "birth certificate"
    derived_from: list = field(default_factory=list)   # parent method names (lineage)
    superseded_by: str = ""

    def node_id(self) -> str:
        return f"METHOD:{self.name}"

    def _src(self) -> str:
        who = self.first_author or self.name
        return self.intro_paper or (f"{who} et al." + (f" {self.year}" if self.year else ""))

    def to_rows(self):
        """Return (nodes, edges) as lists of tuples in kg_memory's shape."""
        nid, src = self.node_id(), self._src()
        nodes = [(nid, self.name, self.category)]
        edges = []
        for role, who in (("first_author", self.first_author), ("last_author", self.last_author)):
            if who:
                aid = f"AUTHOR:{who}"
                nodes.append((aid, who, "Author"))
                edges.append((nid, role, aid, src))
        if self.lab:
            lid = f"LAB:{self.lab}"
            nodes.append((lid, self.lab, "Lab"))
            edges.append((nid, "from_lab", lid, src))
        if self.intro_paper:
            pid = f"PUB:{self.intro_paper}"
            label = self.intro_paper + (f" ({self.year})" if self.year else "")
            nodes.append((pid, label, "Publication"))
            edges.append((nid, "introduced_by", pid, src))
        for parent in self.derived_from:                 # lineage
            edges.append((nid, "derived_from", f"METHOD:{parent}", src))
        if self.superseded_by:
            edges.append((nid, "superseded_by", f"METHOD:{self.superseded_by}", src))
        return nodes, edges


def seed_fused_demo():
    """A tiny FUSED biomedical<->ML graph demonstrating the schema. Authorship here is
    ILLUSTRATIVE (first authors + labs are the reliable signal); a real build populates it
    from a bibliographic source (Semantic Scholar / DBLP / Papers-With-Code).

    Returns (nodes, edges) lists of tuples ready for a kg_memory backend.
    """
    nodes, edges = [], []

    # --- biomedical anchor + the DataModality/Task BRIDGE ---
    nodes += [("MONDO:AF", "atrial fibrillation", "Disease"),
              ("MODALITY:ECG", "ECG (12-lead)", "DataModality"),
              ("MODALITY:genomic", "genomic sequence", "DataModality"),
              ("TASK:seq-clf", "sequence classification", "Task"),
              ("TASK:survival", "time-to-event / survival", "Task"),
              ("LOSS:focal", "focal loss", "Loss"),
              ("LOSS:coxpl", "Cox partial likelihood", "Loss"),
              ("METRIC:auroc", "AUROC", "Metric"),
              ("METRIC:cindex", "C-index", "Metric"),
              ("METRIC:glue", "GLUE score", "Metric")]
    edges += [("MONDO:AF", "manifests_in", "MODALITY:ECG", "clinical knowledge"),
              ("TASK:seq-clf", "evaluated_by", "METRIC:auroc", "methodological"),
              ("TASK:survival", "evaluated_by", "METRIC:cindex", "methodological"),
              ("TASK:survival", "trained_with", "LOSS:coxpl", "methodological")]

    # --- ML methods with authorship + lineage (illustrative attribution) ---
    methods = [
        Method("Transformer", year=2017, first_author="Vaswani", last_author="Polosukhin",
               lab="Google", intro_paper="arXiv:1706.03762"),
        Method("BERT", year=2018, first_author="Devlin", lab="Google",
               intro_paper="arXiv:1810.04805", derived_from=["Transformer"], superseded_by="RoBERTa"),
        Method("RoBERTa", year=2019, first_author="Liu", lab="FAIR/UW",
               intro_paper="arXiv:1907.11692", derived_from=["BERT"]),
        Method("ResNet", year=2015, first_author="He", lab="Microsoft Research",
               intro_paper="arXiv:1512.03385"),
        Method("1D-CNN", category="Architecture"),
    ]
    for m in methods:
        n, e = m.to_rows()
        nodes += n
        edges += e

    # --- effectiveness / bridge edges (stable = trusted; benchmark = LOW trust) ---
    edges += [
        ("METHOD:1D-CNN", "suited_to", "MODALITY:ECG", "methodological"),
        ("METHOD:Transformer", "suited_to", "MODALITY:ECG", "methodological"),
        ("METHOD:Transformer", "used_for", "TASK:seq-clf", "methodological"),
        ("METHOD:1D-CNN", "used_for", "TASK:seq-clf", "methodological"),
        ("METHOD:Transformer", "trained_with", "LOSS:focal", "methodological"),
        # benchmark-relative, time-indexed -> tagged low trust via 'benchmark:' source
        ("METHOD:RoBERTa", "achieves", "METRIC:glue", "benchmark:GLUE 2019"),
        ("METHOD:BERT", "achieves", "METRIC:glue", "benchmark:GLUE 2018"),
    ]

    # dedup nodes by id (first wins)
    seen, uniq = set(), []
    for r in nodes:
        if r[0] not in seen:
            seen.add(r[0]); uniq.append(r)
    return uniq, edges
