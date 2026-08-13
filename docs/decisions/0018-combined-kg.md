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
two node types that carry cross-referenceable ids:
- **Genes → Entrez.** Hetionet uses Entrez (`Gene:5345`); Monarch uses HGNC
  (`HGNC:x`). Crosswalk HGNC→Entrez from the cached HGNC complete set (already pulled
  by `gene_norm`), canonicalizing both to `NCBIGene:<entrez>`.
- **Diseases → MONDO.** Hetionet uses DOID (`DOID:x`); Monarch uses MONDO. Crosswalk
  DOID→MONDO parsed from Monarch's own node `xref` column (11,914 MONDO nodes carry a
  DOID xref) — no extra download.

Both node/edge frames are id-remapped, concatenated, and deduped (Hetionet first, so
genes keep symbol names). Node types without a shared vocabulary (Hetionet DrugBank
compounds vs Monarch CHEBI; Hetionet MeSH symptoms vs Monarch HPO) stay source-
prefixed and simply don't cross-link — they still add edges. Zero new downloads;
reuses the existing Hetionet, Monarch, and HGNC caches.

## Rationale & evidence
- **Merge verified**: **175,001 nodes / 4,176,791 edges**; genes 46,442 (Entrez-
  merged), diseases 36,253 (MONDO). The T2D node (`MONDO:0005148`) carries **both**
  Hetionet edges (`associates`×275 from DisGeNET/GWAS Catalog, `treats`×22) **and**
  Monarch edges (`has_phenotype`, `causes`, `contributes_to` from omim/mondo) — one
  node, multimodal neighborhood.
- **Recovers what each lacked alone**: `T2D ↔ Alzheimer's` 2-hop shared-gene paths
  (OGG1, SOD1, LEP, AKT1) — present via Hetionet's GWAS edges, absent in Monarch-alone
  — now sit in a graph where those genes *also* have Monarch phenotype/PPI context.
- **Known non-overlap** (documented, not a bug): entity types on different vocabularies
  don't cross-link — e.g. "insulin resistance" is a Hetionet MeSH Symptom and a Monarch
  HPO term, which stay separate. Only genes and diseases are harmonized here; extending
  to drugs (DrugBank↔CHEBI) or symptoms (MeSH↔HPO) is future work.

## Consequences
- A ~4.2M-edge integrated graph is available locally as `KG_BACKEND=combined`, giving
  GWAS + phenotype + PPI on shared disease/gene nodes — the multimodal substrate the
  hybrid generator and refinement loop benefit from.
- Heavier to load (Hetionet ~20s + Monarch ~11s + merge); fine under the REPL (loaded
  once). All downstream traversal/scoring code is unchanged.
