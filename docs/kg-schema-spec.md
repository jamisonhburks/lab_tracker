# `kg_schema` — design spec

Status: **draft (pre-implementation)**. Target module: `kg_schema.py`, consumed by
`kg_memory.py`. Some field names are provisional pending the real OptimusKG schema
(the Dataverse download is currently returning HTTP 202; align on recovery).

---

## 1. Purpose

Extend the knowledge-graph layer from bare biomedical triples to **qualified,
contextualized, confidence-bearing assertions**. A domain edge such as
`Gene —associated_with→ Disease` is never unconditional; it is really *"this
**variant** of the gene, found by **this method**, in **this dataset/cohort**,
with **this confidence**."* This spec defines the node types, the reified
association model, the qualifier system, and the confidence fields needed to
represent that — reusing existing standards rather than inventing categories.

Non-goals: implementation code, embedding/geometry choices, UI. Scoring *uses*
these fields (see §7) but the scoring algorithm is specified in `kg_memory`.

---

## 2. Design principles

1. **Reuse standard ontologies; don't invent.** The strongest lesson from the
   literature is that KG quality dominates model size. Bind to established
   vocabularies (below), so nodes interoperate with OptimusKG and the OBO world.
2. **Reify associations.** An edge is a first-class *statement node* that can
   carry evidence, provenance, and qualifiers — not a bare (subject, predicate,
   object) row. Mechanism: Biolink `Association` reification (equivalently
   RDF-star / property-graph edge properties).
3. **Separate the two layers.** Keep *entities of study* (domain) distinct from
   the *epistemic scaffolding* (datasets, methods, cohorts, variants, evidence).
4. **Type the epistemics.** A definitional edge (`is_a`) and a shaky statistical
   association must never be treated as equally certain (see §6).
5. **Upper ontology = BFO/IAO.** Every node type declares a BFO parent so the
   schema plugs into the OBO Foundry hierarchy instead of a bespoke one (§5).

### Standards to bind to

| Concern | Standard |
|---|---|
| Categories, predicates, association qualifiers | **Biolink Model** |
| Upper ontology | **BFO** (material entity / process / ...) + **IAO** (information artifacts) |
| Evidence & provenance | **SEPIO**, **PROV-O**, nanopublication pattern |
| Methods / assays / study design | **OBI**, **STATO** (stats), **EDAM** (bioinformatics ops) |
| Datasets | **DATS**, DataCite DOIs, dbGaP/GEO accessions |
| Variants & consequences | **Sequence Ontology (SO)**, VEP consequence terms, dbSNP |
| Domain ids (CURIEs) | MONDO (disease), HGNC (gene), CHEBI/DRUGBANK (drug), HP (phenotype) |

---

## 3. Layered model

```
Entities of study   Gene, Variant, Protein, Disease, Phenotype, Drug, Pathway     (BFO: material entity)
Investigations      Study, Method, StatisticalModel, Assay                        (BFO: process / occurrent)
Data                Dataset, Cohort/Population, Variable/Measurement, Sample       (IAO: information content entity)
Assertions/Evidence Association (reified), Evidence, Agent                         (IAO: information content entity)
```

The datasets/methods and variant/aspect concepts live in the lower three layers
and attach to domain edges as **qualifiers** (§6).

---

## 4. Node types

Each node: a CURIE `id`, a human `name`, a Biolink `category`, a `bfo_parent`,
and type-specific properties. Ids use standard prefixes where they exist.

| Node type | id namespace | Key properties | BFO parent |
|---|---|---|---|
| Gene | `HGNC:` | symbol, biotype | material entity |
| Variant | `DBSNP:rs…` / HGVS | variant_type (SO), consequence (SO/VEP), allele_freq, gene | material entity |
| Protein | `UNIPROT:` | — | material entity |
| Disease | `MONDO:` | — | material entity (disposition) |
| Phenotype | `HP:` | — | quality |
| Drug | `CHEBI:`/`DRUGBANK:` | — | material entity |
| Pathway | `REACT:`/`GO:` | — | process |
| **Study** | `PMID:`/`DOI:` | year, design | process |
| **Method** | `OBI:`/`EDAM:`/`STATO:` | family (GWAS, Cox, CNN…) | process |
| **Dataset** | `DATASET:`/DataCite DOI | access, modality set | information content entity |
| **Cohort** | internal `COHORT:` | population, ancestry, n, inclusion | information content entity |
| **Variable** | internal `VAR:` | datatype (continuous/categorical/ordinal), unit | information content entity |
| **Association** | internal `ASSOC:` | (see §5) | information content entity |
| **Evidence** | internal `EV:` | evidence_code, agent_type | information content entity |

Notes:
- **Variant** is modeled as a node (richer) *and* summarizable as an edge
  qualifier (lighter) — see §6. Both are supported; ingestion chooses per source.
- **Cohort** and **Variable** are deliberately separate from Dataset so one
  dataset can declare many variables/cohorts, and associations can point at the
  precise variable/population they used.

---

## 5. The reified Association

An `Association` is the heart of the schema: a statement node linking a subject
and object, carrying everything about *how it is known*.

| Field | Type | Meaning |
|---|---|---|
| `id` | CURIE `ASSOC:…` | statement id |
| `subject` | node id | e.g. `HGNC:KCNQ1` |
| `predicate` | Biolink predicate | e.g. `associated_with`, `treats`, `is_a` |
| `object` | node id | e.g. `MONDO:stroke` |
| `epistemic_type` | enum | `definitional \| empirical \| predicted` (§6) |
| `knowledge_level` | Biolink enum | `knowledge_assertion \| statistical_association \| prediction \| observation` |
| `agent_type` | Biolink enum | `manual_agent \| automated_agent \| text_mining_agent` |
| `qualifiers` | struct | variant/aspect, method, dataset, cohort, context (§6) |
| `evidence` | list | one entry per supporting study (§7) |
| `contradicted_by` | list[PMID] | refuting publications |
| `confidence` | float [0,1] | computed (§7); definitional → 1.0 |
| `provenance` | struct | primary_knowledge_source, ingestion agent, timestamp (PROV-O) |

Directionality: stored directed (subject→object); `kg_memory` traversal remains
undirected for discovery, as today.

---

## 6. Qualifiers & epistemic typing

### 6.1 Epistemic type (the `is_a`-is-true point)

| `epistemic_type` | Predicates | Confidence treatment |
|---|---|---|
| `definitional` | `is_a`, `part_of`, `subclass_of` | Axiomatic → 1.0; safe to propagate transitively |
| `empirical` | `associated_with`, `treats`, `predisposes_to` | Probabilistic [0,1], computed from evidence |
| `predicted` | model/computationally inferred | Lower prior; flagged machine-derived |

Traversal and scoring MUST branch on this — never combine a definitional and an
empirical edge as equally certain.

### 6.2 Qualifier bundle (`Association.qualifiers`)

Conditions the empirical claim; each is either a link to a node or a controlled value.

| Qualifier | Target / values | Answers |
|---|---|---|
| `form_or_variant` | Variant node, or SO term (`SNP`, `LoF`, `missense`) | *which aspect of the gene* (msg 3) |
| `aspect` | `rare \| common`, functional consequence severity | rarity/severity → importance |
| `method` | Method node (`GWAS`, `Cox`, `CNN`) | *how it was found* (msg 2) |
| `dataset` | Dataset node (`UK Biobank`) | *in which data* |
| `cohort` | Cohort node | *in which population* (transportability) |
| `context` | population/temporal free qualifiers | conditioning of P(assoc \| context) |

### 6.3 Worked examples

**Dataset/method conditioning (msg 2):**
```
Dataset  UK Biobank  —samples→ Cohort(EU-ancestry, ≥40yr, n≈500k)
                     —contains→ Variable(resting ECG, waveform)
                     Variable(LDL) —has_datatype→ continuous
ASSOC:57 subject=HGNC:KCNQ1 predicate=associated_with object=MONDO:stroke
         qualifiers.method=OBI:GWAS  qualifiers.dataset=UK Biobank
```

**Gene aspect (msg 3):**
```
DBSNP:rs123 —is_a→ SO:SNP  —located_in→ HGNC:KCNQ1
            —has_consequence→ SO:loss_of_function  allele_freq=0.001 (rare)
ASSOC:57 qualifiers.form_or_variant=DBSNP:rs123  qualifiers.aspect=rare_LoF
```
Rarity + consequence severity feed edge importance (rare LoF ≫ common intronic).

---

## 7. Confidence inputs (consumed by `kg_memory` scoring)

Per-association evidence entry:

| Field | Meaning |
|---|---|
| `publication` | PMID/DOI |
| `research_group` | normalized author/lab/institution key (for independence) |
| `dataset` | dataset id (to detect reused-data non-independence) |
| `evidence_code` | e.g. GO `EXP` (experimental) vs `IEA` (inferred) |
| `effect_size`, `p_value`, `correction` | statistical strength |

Aggregation principles (algorithm lives in `kg_memory`, not here):
- Count **independent** groups/datasets, not raw publications; down-weight
  shared authors/labs/datasets.
- Saturating combiner (noisy-OR / Beta posterior) — diminishing returns.
- Weight by source reliability (`evidence_code`, curated vs text-mined).
- Subtract `contradicted_by`.
- **Node-level** confidence: entity-resolution certainty (CURIE mapping) and
  annotation coverage modulate any path through the node.
- **Triple-level** priors: type-compatibility (`Drug–treats–Disease` sensible;
  `Gene–treats–Disease` schema-violating) and structural corroboration.
- **Path-level** (hypothesis scoring): weakest-link × length penalty −
  shared-evidence correlation + **multi-independent-path boost** (Rephetio DWPC).

---

## 8. Physical representation

Polars tables (mirrors current `kg_memory` backend so the swap is minimal):

- `nodes(id, name, category, bfo_parent, props: struct)`
- `associations(id, subject, predicate, object, epistemic_type, knowledge_level,
  agent_type, qualifiers: struct, confidence, provenance: struct)`
- `evidence(assoc_id, publication, research_group, dataset, evidence_code,
  effect_size, p_value, correction)`  — one row per supporting study
- `contradictions(assoc_id, publication)`

Qualifiers/props as Polars struct/list columns. Association-centric edges replace
the current flat `edges` frame; `kg_memory` traversal reads `associations`.

---

## 9. Write path — extraction from publications

Datasets/methods/variants live in Methods & Data-Availability sections.

- **Structured, high-precision:** dataset DOIs (DataCite), accessions (dbGaP/GEO),
  variant ids (dbSNP), method terms (OBI/EDAM lookup).
- **LLM extraction:** a new agent write-tool emits typed records
  `(subject, predicate, object, method, dataset, cohort, variant, consequence,
  effect_size, p_value, correction, publication, research_group)` from paper text,
  written as an `Association` + `evidence` rows. Prior art: Coleridge/"Rich
  Context" dataset-mention extraction.
- Every extracted association carries provenance and enters at
  `epistemic_type=empirical`, `agent_type=text_mining_agent` until curated.

---

## 10. OptimusKG alignment (fill on Dataverse recovery)

OptimusKG is Biolink-native, so it likely already encodes much of §5–6. On the
poller's return, map:

- OptimusKG node id/name/category columns → §4 node fields (confirm CURIE prefixes)
- OptimusKG edge `knowledge_level` / `agent_type` / `qualifiers` / `publications`
  / `primary_knowledge_source` → §5 Association fields (do **not** duplicate;
  reuse what exists)
- Identify which §6 qualifiers OptimusKG already provides vs which we add on ingest

**Open decisions pending real schema:**
1. Variant-as-node vs qualifier-only — which does OptimusKG use?
2. Does OptimusKG expose per-edge `publications` + source (independence signal)?
3. Column names for `subject/predicate/object` (retune `kg_memory` constants).

---

## 11. Phased implementation (each a small PR)

1. **This doc.**
2. `kg_schema.py`: node/association/qualifier dataclasses + enums + CURIE helpers
   (no scraping, no scoring). Demo graph migrated to the Association shape.
3. `kg_memory` reads `associations`; add `epistemic_type` branching to traversal.
4. Confidence scoring in `kg_memory` (§7) + path scoring with multi-path boost.
5. OptimusKG ingest/mapping (§10).
6. Publication extraction write-tool (§9).
