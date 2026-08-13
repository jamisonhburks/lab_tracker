# Changelog

Reverse-chronological summary of substantive changes. Each entry links a PR to the
decision behind it (see `docs/decisions/`). Dates are approximate build dates.

## 2026-08-13
- **Unified provenance view** — `provenance.py`: a deterministic (no-LLM) assembler that
  stitches an experiment's own artifacts (spec, formation method + pre-registration, the
  ordered scientific-op tool ledger, metrics, and the evaluation verdict) into one
  `experiments/{id}/provenance.md` — "how the hypothesis was formed and how it was tested"
  in one place. Verified on H001 (17-op synthetic pipeline) and H002 (13-op real-data
  pipeline; instrumented + re-run, deterministic) (PR #28 · ADR-0022).
- **Tool ledger (intended vs actual, across the loop)** — `tool_ledger.py`: (1) every
  orchestrator run declares the tools it EXPECTS to need (pre-flight plan) and records the
  ones it ACTUALLY calls in order → intended→actual→diff trace; (2) the specialist records
  its skill-call trace; (3) each experiment's `run.py` records its actual SCIENTIFIC ops
  (data gen/fetch, per-gene tests, `multipletests`, effect sizes, plotting) →
  `experiments/{id}/tool_ledger.json`. Verified: orchestrator run-11 (planned 4/used 3;
  ledger caught the 14B over-planning 11→3, fixed via a selectivity nudge); H001 emitted
  its 17-step scientific trace. Only the pipeline subagents' harness tools (Write/Bash)
  remain out of scope (harness telemetry) (PR #27 · ADR-0021).
- **H002 — first REAL-DATA run through the loop** — the T2D↔AD shared-gene panel tested
  on public GEO brain expression (GSE48350 discovery + GSE122063 replication, prep-matched
  bulk-vs-bulk, covariate-adjusted, panel-restricted Bonferroni+BH, cross-platform
  direction replication). **Honest null**: no central gene BH-significant + replicated
  (APOE borderline p_bh≈0.054, decreased); 3 panel BH hits all reversed sign in
  replication; replication arm underpowered (n≈23, power 0.09–0.22) so the null is bounded,
  not a refutation. Human-approved (draft→approved gate); runner caught the AD='AA' GEO
  coding gotcha. Contrast with H001's synthetic success — the loop reports real nulls
  faithfully. `hypotheses/H002*.yaml`, `experiments/H002/`, `reports/H002_evaluation.md`
  (PR #26 · ADR-0020).
- **Closed the scientific loop** — orchestrated `hypothesis-planner → code-implementer
  → experiment-runner → results-evaluator` (separation of concerns) to take a KG-
  generated hypothesis through formalize → implement → run → evaluate. Demo H001 (T2D↔AD
  shared genes) ran end-to-end on synthetic data with known ground truth: recovered 7/7
  planted genes at BH-FDR<0.05 & |d|≥0.5 across 3 seeds, 1 expected FDR false positive
  (Bonferroni rejected it). Validates the loop + stats machinery, not biology; evaluator
  caught + we fixed a duplicate-logging bug. Adds `hypotheses/H001*.yaml`,
  `experiments/H001/`, `src/utils/log_run_metadata.py`, `reports/H001_evaluation.md`
  (PR #25 · ADR-0020).
- **Claude specialist for scientific tool use** — `run_specialist(task)` delegates
  scientific computation to a Claude agent (`specialist.py`) that runs k-dense Agent
  Skills (`list_skills`/`read_skill`/`run_bash`). Skills are an external gitignored
  library with a curated allow-list; `llm.chat` gains a per-call backend override so
  the local orchestrator delegates one step to Claude. Verified: discovery/read/execute
  work (ran a skill to produce a disclosure-controlled cohort table); Claude driver
  401-not-400. Live round-trip needs an API key (PR #24 · ADR-0019).
- **Combined KG (Hetionet + Monarch)** — `KG_BACKEND=combined`: `load_combined()`
  harmonizes genes→Entrez (HGNC crosswalk), diseases→MONDO (DOID xrefs), and drugs→
  CHEBI (DrugBank xrefs), merging both graphs → ~174k nodes / 4.2M edges. A disease
  node inherits GWAS gene edges (Hetionet) AND phenotype/PPI edges (Monarch); drugs
  merge onto CHEBI (metformin→treats→T2D). Recovers T2D↔Alzheimer shared genes
  Monarch-alone lacked. MeSH↔HPO symptoms not merged (no in-data crosswalk, low value).
  A local slice of PrimeKG; no new downloads (PR #23 · ADR-0018).
- **Monarch KG backend** — `KG_BACKEND=monarch`: `load_monarch()` loads a focused
  human subgraph (~148k nodes / 1.9M edges) with 36k MONDO diseases + HPO phenotypes
  (vs Hetionet's 137 diseases, no phenotypes). Strong for phenotype/Mendelian
  hypotheses (Marfan↔Loeys-Dietz via shared phenotypes); sparse on GWAS gene-disease
  (complementary to Hetionet, not a replacement). PrimeKG/OptimusKG stayed Dataverse-
  202-blocked. Adds category-aware `_resolve` + STRING low-trust (PR #23 · ADR-0017).
- **Refinement loop** — `refine_hypothesis`: per bridge, novelty (cheap PubMed
  count) filters which links deserve the expensive `curate_literature` + `criticize`
  pass; triages each as known / supported-real / spurious and persists verified links
  to the curated KG. Verified end-to-end on AF↔stroke (`warfarin` supported, `KCNQ1`
  speculative); added `-1` `unknown_bridge` guard + rate-limit backoff (PR #22 · ADR-0016).
- **Novelty flag + hybrid generation** — `novelty.check_novelty` (rediscovery vs
  new juxtaposition, judged on the A–bridge–C triple) and `generate_hypothesis`
  (KG retrieves the subgraph → model synthesizes a mechanism CONSTRAINED to it →
  grounding + novelty regularize the claim). Novelty flag reproduces the lit-agent's
  gene tiering independently (CTF1 → `novel_bridge`) (PR #21 · ADR-0015).
- **LLM adapter** — `llm.py`: model reached via `chat()`; Ollama ↔ Claude is a
  config flag (`LLM_BACKEND`). Ollama path verified; Anthropic best-effort
  (PR #19 · ADR-0014).
- **Critic hardened** — accession pre-filter + multi-vote + expanded 12-case eval;
  gold set caught an accession gap → fixed to 1.00 (PR #18 · ADR-0013).
- **Critic agent** — adversarial verifier (`criticize_curated_kg`) + test-driven
  eval harness (`eval_critic.py`); catches hallucinations/junk while preserving
  novel valid links (PR #17 · ADR-0013).
- **B4 persistent KG (REPL)** — `python agent.py` with no arg keeps the KG + model
  warm across questions (PR #15).
- **B3 permutation-null calibration** — `calibrate_link`: percentile/p-value vs a
  degree-matched null, exposing density inflation (PR #14 · ADR-0010).
- **B2 grounding → confidence** — KG grounding folded into the confidence score;
  novel/off-graph never penalized (PR #13 · ADR-0008).
- **B1.6 type-aware normalization** — HGNC gene dictionary + BioLORD; fixes
  `IL8 → CXCL8` (PR #12 · ADR-0009).
- **B1.5 semantic normalization** — BioLORD (opt-in); catches disease synonyms;
  found to fail on gene symbols (PR #11 · ADR-0009).
- Curator: better synthesizer — per-paper extraction (exact PMID) + study stats
  (PR #9 · ADR-0011).

## 2026-08-12
- **B1 entity normalization** — canonical-node dedup, junk flagged (PR #10 · ADR-0009).
- **Synthesizer → KG-curator** — writable KG, literature→KG loop (PR #9 · ADR-0011).
- **Multi-agent architecture** design note (PR #8 · ADR-0011).
- **KG-as-verifier grounding check** — novel ≠ false (PR #7 · ADR-0008).
- **Power-weighted negative evidence** + confidence scorer (PR #6 · ADR-0007).
- **Reified-association schema** — phase 2 + spec (PRs #1, #5 · ADR-0006).
- **Hypothesis tools** — realism (degree-weighted) + experiment planner (PR #4).
- **Hetionet backend** + scalable indexed traversal (PR #2 · ADR-0004).
- Private repo + git workflow established (ADR-0012).

## 2026-08-11 (pre-repo prototype)
- Local Qwen3-14B agent via Ollama (ADR-0001).
- Layered memory (working / episodic / semantic) with claim-level provenance
  (ADR-0002).
- Retrieval scorers: recency-decay, hybrid BM25+dense (RRF), MMR, threshold
  (ADR-0003).
- KG (ontological) memory: typed traversal, A→B→C path discovery.

## Deferred / open
- **OptimusKG** — Dataverse locked (HTTP 202, likely 2.0 reingest); Hetionet used
  meanwhile, one-call swap when it unlocks (ADR-0004).
- Hybrid over pure KG-pretraining, pending honest (time-sliced/cold-start) eval
  (ADR-0005).
- Next specialist: **critic** agent. Autonomous execution half needs the compute
  cluster + human-in-the-loop.
