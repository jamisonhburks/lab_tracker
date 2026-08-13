# ADR-0006: Reified-association schema (Biolink + BFO/IAO)

- **Date:** 2026-08-12
- **Status:** Accepted

## Context
A biomedical edge is never unconditional — it's "*this variant* of the gene, by
*this method*, in *this dataset/cohort*, with *this confidence*." A bare (subject,
predicate, object) triple can't carry that.

## Options considered
- Bare triples + a side table of sources.
- **Reified associations**: each edge is a first-class statement node carrying
  evidence, provenance, qualifiers, epistemic type, confidence.

## Decision
**Reify associations**, and **reuse standard ontologies** rather than invent:
Biolink (categories, predicates, qualifiers, `knowledge_level`/`agent_type`),
BFO/IAO upper ontology, SEPIO/PROV-O (evidence), OBI/STATO/EDAM (methods),
Sequence Ontology (variants), MONDO/HGNC/CHEBI (ids).

## Rationale & evidence
- Datasets/methods and gene-aspects (SNP/rare/LoF) become **qualifiers** on the
  association — expressing "conditioned on the method" and "which aspect of the
  gene" without exploding the graph.
- Reusing standards makes nodes interoperate with OptimusKG and the OBO world (the
  "KG quality dominates" lesson).
- Bulk storage/traversal stay in Polars (fast on millions of edges); the typed
  `Association` represents one edge richly when reasoning about *how it's known*.

## Consequences
- Implemented as `kg_schema.py` (phase 2) + the design in
  `docs/kg-schema-spec.md`. Feeds the confidence scorer (ADR-0007) and the curator
  (ADR-0011). Full extraction of datasets/methods/variants is a later phase.
