# ADR-0018: Combined KG (Hetionet + Monarch) — a local slice of PrimeKG

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
Hetionet and Monarch are complementary (ADR-0017): Hetionet is GWAS-rich on
disease→gene but has 137 diseases and no phenotypes; Monarch has 36k MONDO diseases +
HPO phenotypes but is sparse on GWAS gene-disease. PrimeKG's value is precisely that
it *integrates* many such sources onto common vocabularies. With PrimeKG itself
Dataverse-202-blocked, we can reconstruct the useful slice by merging the two KGs we
already have — if we can resolve the same entity to one node across both.

## Decision
Add `load_combined()` (`KG_BACKEND=combined`). It loads both graphs and harmonizes the
three node types that carry cross-referenceable ids, all crosswalked from data already
on disk (zero new downloads):
- **Genes → Entrez.** Hetionet uses Entrez (`Gene:5345`); Monarch uses HGNC
  (`HGNC:x`). Crosswalk HGNC→Entrez from the cached HGNC complete set (already pulled
  by `gene_norm`), canonicalizing both to `NCBIGene:<entrez>`.
- **Diseases → MONDO.** Hetionet uses DOID; Monarch uses MONDO. Crosswalk DOID→MONDO
  parsed from Monarch's node `xref` column (11,914 MONDO nodes carry a DOID xref).
- **Drugs → CHEBI.** Hetionet uses DrugBank (`Compound:DBx`); Monarch uses CHEBI.
  Crosswalk DrugBank→CHEBI parsed from Monarch's CHEBI node `xref` column (2,211 CHEBI
  nodes carry a `drugbank:` xref) — brings Hetionet's rich drug edges (treats/binds/
  regulates) onto shared chemical nodes, fixing Monarch's near-zero drug coverage.

Both node/edge frames are id-remapped, concatenated, and deduped (Hetionet first, so
genes/drugs keep their symbol/drug names).

**Not harmonized — symptoms (MeSH↔HPO).** Hetionet symptoms are MeSH, Monarch
phenotypes are HPO, but **0 of 11,485** Monarch HP nodes carry a MeSH xref — so unlike
the three above, this crosswalk is *not* in our data. It would need an external HPO
ontology download, the MeSH↔HPO mapping is semantically fuzzy, and the payoff is small
(Hetionet has only 438 symptoms / 3,357 `presents` edges vs Monarch's 20k HPO / 425k).
Deferred as not worth the download. Hetionet symptoms stay source-prefixed and
uncross-linked.

## Rationale & evidence
- **Merge verified**: **175,001 nodes / 4,176,791 edges**; genes 46,442 (Entrez-
  merged), diseases 36,253 (MONDO). The T2D node (`MONDO:0005148`) carries **both**
  Hetionet edges (`associates`×275 from DisGeNET/GWAS Catalog, `treats`×22) **and**
  Monarch edges (`has_phenotype`, `causes`, `contributes_to` from omim/mondo) — one
  node, multimodal neighborhood.
- **Recovers what each lacked alone**: `T2D ↔ Alzheimer's` 2-hop shared-gene paths
  (OGG1, SOD1, LEP, AKT1) — present via Hetionet's GWAS edges, absent in Monarch-alone
  — now sit in a graph where those genes *also* have Monarch phenotype/PPI context.
- **Drugs merged and verified**: 1,091 of ~1,552 Hetionet compounds align onto CHEBI;
  `metformin` → `CHEBI:6801` carrying Hetionet's `treats`/`binds`/`regulates`/side-
  effect edges, and `metformin —treats→ T2D` resolves — drug-repurposing capability
  Monarch alone lacked (56 `treats` edges → Hetionet's 755+ now on shared nodes).
- **Known non-overlap** (documented, not a bug): types on vocabularies we don't
  harmonize don't cross-link — e.g. "insulin resistance" is a Hetionet MeSH Symptom and
  a Monarch HPO term, which stay separate (see the MeSH↔HPO note above). Genes,
  diseases, and drugs are harmonized; symptoms are the remaining gap.

## Consequences
- A ~4.2M-edge integrated graph is available locally as `KG_BACKEND=combined`, giving
  GWAS + phenotype + PPI on shared disease/gene nodes — the multimodal substrate the
  hybrid generator and refinement loop benefit from.
- Heavier to load (Hetionet ~20s + Monarch ~11s + merge); fine under the REPL (loaded
  once). All downstream traversal/scoring code is unchanged.
