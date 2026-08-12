"""kg_schema — the reified-association type system for the knowledge graph.

Phase 2 of docs/kg-schema-spec.md: the node / association / qualifier types,
epistemic typing, and CURIE helpers. NO scoring and NO scraping here — those are
later phases (confidence scoring in kg_memory; extraction as a write-tool).

Why a separate representation: bulk storage and traversal stay in Polars
(kg_memory) because that's fast on millions of edges. These dataclasses are for
representing ONE edge/path richly — when we need to reason about *how* a fact is
known: its evidence, provenance, qualifiers, and certainty. `lift_edge()` turns a
flat (subject, predicate, object, source) tuple into a reified Association.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# --------------------------------------------------------------------------- #
# Epistemic typing — a definition (is_a) must never be treated like a shaky    #
# correlation. Values align to the Biolink Model where one exists.             #
# --------------------------------------------------------------------------- #

class EpistemicType(str, Enum):
    DEFINITIONAL = "definitional"   # is_a / part_of — true within the ontology
    EMPIRICAL = "empirical"         # associates / treats — uncertain, evidence-based
    PREDICTED = "predicted"         # computationally inferred


class KnowledgeLevel(str, Enum):    # Biolink knowledge_level
    KNOWLEDGE_ASSERTION = "knowledge_assertion"
    STATISTICAL_ASSOCIATION = "statistical_association"
    PREDICTION = "prediction"
    OBSERVATION = "observation"
    NOT_PROVIDED = "not_provided"


class AgentType(str, Enum):         # Biolink agent_type
    MANUAL = "manual_agent"
    AUTOMATED = "automated_agent"
    TEXT_MINING = "text_mining_agent"
    NOT_PROVIDED = "not_provided"


class Direction(str, Enum):         # does a study support or refute the claim?
    SUPPORTS = "supports"
    REFUTES = "refutes"


class RiskOfBias(str, Enum):        # methodology quality of a study
    LOW = "low"
    SOME = "some"
    HIGH = "high"


# How much a study's result should move belief, by risk-of-bias (used when a
# study reports no explicit statistical power). A high-bias study is barely
# informative — its null could be a methodology artifact, not a true negative.
_ROB_INFORMATIVENESS = {RiskOfBias.LOW: 0.8, RiskOfBias.SOME: 0.5, RiskOfBias.HIGH: 0.2}


# BFO / IAO upper-ontology parent per node category (spec §3, §5).
BFO_PARENT = {
    "Gene": "material entity", "Variant": "material entity",
    "Protein": "material entity", "Compound": "material entity",
    "Drug": "material entity", "Anatomy": "material entity",
    "Disease": "material entity",
    "Phenotype": "quality", "Symptom": "quality", "Side Effect": "quality",
    "Pathway": "process", "Biological Process": "process",
    "Molecular Function": "process", "Study": "process", "Method": "process",
    "Dataset": "information content entity",
    "Cohort": "information content entity",
    "Variable": "information content entity",
    "Association": "information content entity",
}

_DEFINITIONAL_PREDICATES = ("is_a", "subclass", "part_of")
_PREDICTED_PREDICATES = ("predicted", "inferred", "imputed")


def classify_epistemic(predicate: str) -> EpistemicType:
    """Infer an edge's epistemic type from its predicate (substring match)."""
    p = predicate.lower()
    if any(k in p for k in _DEFINITIONAL_PREDICATES):
        return EpistemicType.DEFINITIONAL
    if any(k in p for k in _PREDICTED_PREDICATES):
        return EpistemicType.PREDICTED
    return EpistemicType.EMPIRICAL


def split_curie(node_id: str) -> tuple[str, str]:
    """'Disease:DOID:8778' -> ('Disease', 'DOID:8778')."""
    prefix, _, local = node_id.partition(":")
    return prefix, local


def bfo_parent(category: str) -> str:
    return BFO_PARENT.get(category, "entity")


# --------------------------------------------------------------------------- #
# The reified association and its parts.                                       #
# --------------------------------------------------------------------------- #

@dataclass
class Qualifiers:
    """Conditions on an empirical claim (spec §6.2). All optional."""
    form_or_variant: str | None = None   # variant node or SO term (SNP / LoF / missense)
    aspect: str | None = None            # rare | common, consequence severity
    method: str | None = None            # Method node / OBI term (GWAS, Cox, CNN)
    dataset: str | None = None           # Dataset node (e.g. UK Biobank)
    cohort: str | None = None            # Cohort node (population)
    context: str | None = None           # free population / temporal qualifier

    def active(self) -> dict:
        return {k: v for k, v in vars(self).items() if v is not None}


@dataclass
class Evidence:
    """One study bearing on an association — supporting OR refuting (spec §7).

    Negative results are first-class here: `direction=REFUTES`. But a refuting
    study is only as informative as it is well-powered — an underpowered null
    ('absence of evidence') should barely move belief, whereas a well-powered
    null ('evidence of absence') should. `informativeness()` encodes that.
    """
    publication: str | None = None       # PMID / DOI
    source: str | None = None            # knowledge source / database
    research_group: str | None = None    # normalized lab/author — independence signal
    dataset: str | None = None           # reused-data detection
    evidence_code: str | None = None     # EXP (experimental) | IEA (inferred) | ...
    effect_size: float | None = None
    p_value: float | None = None
    correction: str | None = None        # Bonferroni | BH | ...
    direction: Direction = Direction.SUPPORTS
    sample_size: int | None = None
    power: float | None = None           # 1 - beta, if reported/estimable
    ci_low: float | None = None          # effect confidence interval
    ci_high: float | None = None
    risk_of_bias: RiskOfBias | None = None

    def informativeness(self) -> float:
        """How much this study's result should move belief, in [0, 1].

        Bayesian intuition: an underpowered study's null is uninformative
        (likelihood ratio ~1). Prefer reported power; fall back to risk-of-bias;
        otherwise assume moderately informative.
        """
        if self.power is not None:
            return max(0.0, min(1.0, self.power))
        if self.risk_of_bias is not None:
            return _ROB_INFORMATIVENESS[self.risk_of_bias]
        return 0.5

    def covers_effect(self, threshold: float) -> bool:
        """Does the CI still admit an effect of at least `threshold`?

        A null result whose interval covers a meaningful effect is INCONCLUSIVE
        ('absence of evidence'), not a true negative. Needs a domain threshold.
        """
        if self.ci_low is None or self.ci_high is None:
            return False
        return self.ci_high >= threshold or self.ci_low <= -threshold


@dataclass
class Association:
    """A reified edge: a statement plus how it is known (spec §5)."""
    subject: str
    predicate: str
    object: str
    epistemic_type: EpistemicType = EpistemicType.EMPIRICAL
    knowledge_level: KnowledgeLevel = KnowledgeLevel.NOT_PROVIDED
    agent_type: AgentType = AgentType.NOT_PROVIDED
    qualifiers: Qualifiers = field(default_factory=Qualifiers)
    evidence: list[Evidence] = field(default_factory=list)  # supporting AND refuting
    confidence: float | None = None      # computed later (phase 4)

    @property
    def is_definitional(self) -> bool:
        return self.epistemic_type is EpistemicType.DEFINITIONAL

    def supporting(self) -> list[Evidence]:
        return [e for e in self.evidence if e.direction is Direction.SUPPORTS]

    def refuting(self) -> list[Evidence]:
        return [e for e in self.evidence if e.direction is Direction.REFUTES]

    def independent_sources(self, direction: Direction | None = None) -> set[str]:
        """Distinct sources (compound 'A, B' strings atomized), optionally by direction."""
        out: set[str] = set()
        for ev in self.evidence:
            if direction is not None and ev.direction is not direction:
                continue
            if ev.source:
                out.update(t.strip() for t in ev.source.split(",") if t.strip())
        return out

    def render(self) -> str:
        lines = [
            f"{self.subject} —{self.predicate}→ {self.object}",
            f"  epistemic: {self.epistemic_type.value} ({self.knowledge_level.value})",
        ]
        srcs = self.independent_sources(Direction.SUPPORTS)
        if srcs:
            lines.append(f"  supporting sources ({len(srcs)}): {', '.join(sorted(srcs))}")
        if self.refuting():
            ref = self.refuting()
            powered = sum(1 for e in ref if e.informativeness() >= 0.5)
            lines.append(f"  refuting studies: {len(ref)} "
                         f"({powered} adequately-powered, {len(ref) - powered} weak)")
        if self.qualifiers.active():
            lines.append(f"  qualifiers: {self.qualifiers.active()}")
        if self.confidence is not None:
            lines.append(f"  confidence: {self.confidence:.2f}")
        return "\n".join(lines)


_KL_FOR_EPISTEMIC = {
    EpistemicType.DEFINITIONAL: KnowledgeLevel.KNOWLEDGE_ASSERTION,
    EpistemicType.EMPIRICAL: KnowledgeLevel.STATISTICAL_ASSOCIATION,
    EpistemicType.PREDICTED: KnowledgeLevel.PREDICTION,
}


def lift_edge(subject: str, predicate: str, object: str, source: str = "",
              qualifiers: Qualifiers | None = None) -> Association:
    """Turn a flat KG edge into a reified Association with inferred typing.

    Bridges kg_memory's Polars edges into the rich type system: classifies the
    epistemic type from the predicate and wraps the source string as Evidence.
    """
    et = classify_epistemic(predicate)
    evidence = [Evidence(source=s.strip()) for s in source.split(",") if s.strip()]
    return Association(
        subject=subject, predicate=predicate, object=object,
        epistemic_type=et, knowledge_level=_KL_FOR_EPISTEMIC[et],
        qualifiers=qualifiers or Qualifiers(), evidence=evidence,
    )


if __name__ == "__main__":   # runnable demo: two edges, different epistemics
    empirical = lift_edge(
        "Disease:DOID:8778", "resembles", "Disease:DOID:8577",
        source="MEDLINE cooccurrence, GWAS Catalog",
    )
    definitional = lift_edge("DBSNP:rs123", "is_a", "SO:SNP")
    definitional.qualifiers = Qualifiers(form_or_variant="LoF", aspect="rare")

    print("=== empirical association (from a real Hetionet-shaped edge) ===")
    print(empirical.render())
    print("\n=== definitional association (variant taxonomy) ===")
    print(definitional.render())
