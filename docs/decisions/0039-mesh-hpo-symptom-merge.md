# ADR-0039: MeSH↔HPO symptom/phenotype merge in the combined KG

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The `combined` backend (ADR-0018) fuses Hetionet + Monarch by harmonizing shared entities onto
common vocabularies: genes→Entrez, diseases→MONDO, drugs→CHEBI. Symptoms/phenotypes were the
one class left un-merged — Hetionet encodes **Symptom** nodes as **MeSH** descriptors, Monarch
encodes **PhenotypicFeature** nodes as **HPO** terms — so the same clinical concept (Fatigue,
Diplopia, Chest pain) existed as two disconnected nodes. A Hetionet `disease→symptom` edge and a
Monarch `phenotype→gene` edge could never meet, fragmenting exactly the phenotype-mediated paths
that hypothesis generation cares about.

The other crosswalks parse a cross-reference column (DOID/DrugBank xrefs on Monarch nodes). That
route is unavailable here: **Monarch's HPO nodes carry no MeSH xref** — their xrefs are UMLS /
SNOMED / NCIT (verified: 0 of 11 485 HPO nodes have a MeSH xref). UMLS would bridge MeSH↔HPO but
is license-gated. So an xref crosswalk isn't possible with freely-available, already-cached data.

## Decision
Add a **lexical, precision-first** crosswalk: match each Hetionet MeSH symptom to an HPO term by
**exact name + exact-synonym**, with two cheap normalizations that close most of the gap —
de-pluralization (`Seizures`→`seizure`) and **MeSH inversion** (`Vision, Low`→`low vision`;
`Aphasia, Conduction`→`conduction aphasia`). `_mesh_symptom_to_hpo` builds the map; `load_combined`
folds it into the existing Hetionet→canonical id map and applies it through the same
`_apply_id_map` path as genes/diseases/drugs.

**Precision over recall, deliberately.** A miss just leaves a node un-linked (the prior behavior);
a *wrong* merge would forge a false mechanistic path and corrupt grounding. So matching is
exact-name/exact-synonym only — no fuzzy/substring matching — and first-HPO-term-wins.

## Rationale & evidence
- **Coverage is honest and the residue is mostly correct non-matches.** 183 / 438 Hetionet
  symptoms map to HPO. The unmatched ~255 are dominated by MeSH "symptoms" that are actually
  **diseases/syndromes** (Huntington Disease, WAGR syndrome, Rubinstein-Taybi) — which *should not*
  map to a phenotype; leaving them unmatched is the correct outcome, not a gap.
- **Spot-checked correct**: Fatigue→HP:0012378, Diplopia→HP:0000651, Chest Pain→HP:0100749;
  inversion recovers Syncope Vasovagal→HP:0012668, Obstructive Sleep Apnea→HP:0002870, etc.
- **Same proven mechanism**: reuses `_apply_id_map`, identical to the verified gene/disease/drug
  harmonization — the only new logic is how the map is *sourced* (name match vs xref parse).
- **Integration**: the loaded `combined` graph (173 727 nodes / 4.18 M edges) has **426 915 edges
  touching HP nodes, from BOTH sources** — Hetionet's disease→symptom `presents` edges (source
  `MEDLINE cooccurrence`) and Monarch's `hpo-annotations` / `omim` / `orphanet`. Concretely,
  `HP:0012378` (Fatigue) now carries 511 edges including Hetionet `melanoma —presents→ Fatigue`
  alongside Monarch's phenotype annotations — the two sources meeting at the one node, which before
  the merge was a disconnected `Symptom:D005221`.

## Consequences
- Phenotype-mediated cross-source paths now exist: e.g. a Hetionet disease and a Monarch gene can
  connect through a shared symptom/phenotype, enriching `find_paths`/grounding for the combined KG.
- The merge is scoped to `combined`; other backends are untouched.
- Recall is intentionally capped; if a licensed UMLS Metathesaurus is ever available, a
  MeSH→CUI←HPO crosswalk could lift coverage — additive to this lexical map, not a replacement.
