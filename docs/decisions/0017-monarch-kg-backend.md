# ADR-0017: Monarch KG backend (larger, named, phenotype-rich)

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
Hetionet v1.0 (2017) has only **137 diseases** and no phenotype layer — the main
limit felt in hypothesis generation. We wanted a larger KG. PrimeKG (the preferred
target) and OptimusKG are both on Harvard Dataverse and both return **HTTP 202** for
every access path (dataset API, direct file, `?format=original`, `gbrecs`) — the same
lock that blocked OptimusKG for days. The PrimeKG GitHub repo ships only construction
scripts, not data; rebuilding needs ~20 license-gated sources. So PrimeKG is
unreachable now.

## Options considered
- **Monarch KG** — reachable (329MB tarball), human-named, biolink-typed, MONDO
  diseases + HPO phenotypes, real per-edge provenance.
- **DRKG** — reachable, 5.9M triples, but bare-ID nodes (needs a naming layer).
- **Retry PrimeKG** — poll the 202 (user declined; may never clear).

## Decision
Add `load_monarch()` as a `KG_BACKEND=monarch` option. Because the backend contract
is just two DataFrames (`id/name/category`, `subject/predicate/object/source`), the
loader is the only new code — all traversal/DWPC/calibration/grounding/normalization
run unchanged. We load a **focused human subgraph** (the full graph is 1.6M nodes /
15.8M edges, mostly cross-species): keep Disease/Gene/PhenotypicFeature/Protein/
ChemicalEntity/Pathway; human-restrict genes/proteins; HPO-only phenotypes; drop
ontology taxonomy/equivalence predicates (`subclass_of`, `same_as`, `homologous_to`,
…) so paths are mechanistic, not taxonomic. Result: **~148k nodes / 1.9M edges**,
loads in ~11s.

## Rationale & evidence
- **Disease coverage win**: 36,252 MONDO diseases vs Hetionet's 137. `Marfan
  syndrome`, `cystic fibrosis` (absent from Hetionet) resolve with full HPO
  phenotype profiles.
- **Distinct strength — phenotype-mediated hypotheses**: `Marfan ↔ Loeys-Dietz`
  yields rich shared-phenotype paths (aortic aneurysm, pectus excavatum, myopia)
  that Hetionet structurally cannot produce (no phenotype layer).
- **Honest weakness — GWAS gene-disease is sparse**: only ~8k
  `gene_associated_with_condition` + ~7k `causes` edges (mostly Mendelian), so the
  complex-disease shared-gene flow that powered the Hetionet T2D↔Alzheimer's result
  finds **no path**. Hetionet stays better for GWAS-style links; the two are
  complementary, not a replacement. Drug→disease is near-absent (56 `treats` edges) —
  Monarch is not for drug repurposing.
- **Fixes the run surfaced**: (a) with 148k nodes a name can collide across
  categories — `_resolve` now prefers the hypothesis-relevant type (Disease/Gene >
  Phenotype), so `Alzheimer disease` resolves to the disease, not the HPO term; (b)
  STRING added to `_LOW_TRUST` (its PPIs include predicted/text-mined edges) so
  PPI-only paths ground as "weak."
- **ICD-10 / OMIM / SNOMED / Orphanet** are carried as **xrefs** on MONDO nodes (not
  traversable namespaces) — useful for future crosswalking.

## Consequences
- A larger, named, phenotype-rich KG is available today without waiting on Dataverse.
- Backend choice is now a real methodological lever: Hetionet for GWAS/drug links,
  Monarch for phenotype/rare-disease mechanism. Same tools, different substrate.
- `data/` (the 330MB cache) stays gitignored.
