# Changelog

Reverse-chronological summary of substantive changes. Each entry links a PR to the
decision behind it (see `docs/decisions/`). Dates are approximate build dates.

## 2026-08-14
- **Resilient live retrieval (`net.py`)** — one shared helper (`urlopen_retry` / `fetch_bytes`
  / `fetch_text`) that every external fetch routes through (PubMed, arXiv, Monarch, Hetionet,
  HGNC). Retries only transient failures (connection/timeout, HTTP 429/5xx; 404 fails fast)
  with exponential backoff + jitter — tenacity if installed, else an equivalent manual loop
  (so the dep is OPTIONAL). Replaced novelty's bespoke retry loop; deleted all raw `urlopen`
  call sites. Verified both paths (retry-then-succeed, 404 fail-fast, 503 retry, exhaust-
  reraise) (PR #42 · ADR-0035).
- **`scaffold.py` onboarding helper** — automates the mechanical half of the `new-project` /
  `conform-project` flows (stdlib-only, no deps). `new` builds the standard tree + fills
  `CLAUDE.md`/`README.md` placeholders (computed substrate path, status `scaffolding`) +
  `.gitignore` + a `notes/00_charter.md` stub listing the substrate checks for the next
  session to run; `conform` is NON-destructive (missing dirs + files only, never overwrites).
  Idempotent (`--force` to overwrite). Deliberately does the copy-and-fill, NOT the thinking
  (grounding/hypotheses stay agent-driven). Verified: fill, idempotency, non-destructive
  conform (PR #41 · ADR-0034).
- **Lab-standard onboarding playbook** — a self-describing layer (docs only) so a fresh
  session can scaffold a new project or conform an existing one to the standard, then keep
  future sessions on-standard. Root `AGENTS.md` routes by intent → `lab-standard/`:
  `START-HERE`, `new-project`, `conform-project`, `hypothesis-workflow`,
  `experiment-workflow`, `promotion` (local semantic → shared WIP → shared consensus),
  `project-structure`, `using-the-substrate`, plus `templates/` (`hypothesis.yaml` with
  explicit `provenance:`/`validity_gates:` blocks, `project-README.md`, and
  `project-CLAUDE.md` dropped into each project so the rules travel with the work). No new
  code/deps — pure guidance over the existing MCP tools, 4-agent split, gates, and
  `contribute()` (PR #40 · ADR-0033).
- **`contribute()` write-path** — `contribute.py`: findings flow into shared CONSENSUS
  (the one gated tier) — normalized, critic-gated (literature→abstract, experiment→committed
  provenance), routed conservatively (novel/contradictory→pending_review, corroborating-
  supported→auto_merged, junk→rejected), appended with ATTRIBUTION; auto-merge aggregates
  evidence + confidence. Exposed as MCP shared-tier tools (contribute_finding, review_queue).
  Git deploy: append=PR, critic=CI, review=approval. Also fixed a latent cold-start bug in
  `_norm_index`. Verified all 3 routes (PR #39 · ADR-0032).
- **Three-tier substrate scoping + WIP group semantics** — `SUBSTRATE_SCOPE`
  (personal|shared|all) on the MCP server: PERSONAL (episodic + personal semantic, local),
  SHARED WIP (`list_active_work` — every tracked hypothesis/experiment/campaign with STATUS
  + validity-gate counts, provisional/un-gated), SHARED CONSENSUS (critic-gated curated
  findings). Run a shared deployment (hosted, over git-repo KG) + a personal one (local).
  Distinction is CONCLUSION vs PROCESS: process is shareable mid-flight, findings are gated
  (PR #38 · ADR-0031).
- **KG-grounded method selection (Stage 3)** — `method_select.recommend_methods` turns
  'what method for this data?' into a GRAPH TRAVERSAL (modality→suited_to→used_for→
  trained_with→evaluated_by + caveats + authorship + trust split), backend-independent.
  Wired into `propose_experiment` (appends after the study-design essentials) and exposed
  as a tool. Verified: ECG→Transformer; T2D event-based→Transformer/GRU vs tabular→XGBoost
  (PR #36 · ADR-0029).
- **MCP substrate server** — `mcp_server.py`: exposes the substrate over MCP (local
  stdio) so a fresh Claude session (Claude Desktop / Claude Code) can think WITH it —
  ground_claim, calibrate_link, check_novelty, find_paths, query_curated_findings,
  recall_prior_work, recommend_methods, propose_experiment + audit resources
  (provenance/report/ledger/hypothesis). No LLM inside (substrate, not thinker); returns
  evidence, not just answers. Verified: 9 tools + 5 resources register, live call returns
  grounding. Realizes 'substrate, not thinker' (PR #37 · ADR-0030).
- **ML layer — Stage 1 curated expansion** — grew the arXiv-seeded method set 13→61
  seminal methods (NLP/CV/graph/generative/SSL/RL/tabular) with REAL first/last-author +
  year from arXiv, hand-curated lineage, and a title-keyword GUARD that drops any mistyped
  id before it can mis-attribute authorship (all 61 passed). Added XGBoost so tabular-EHR
  bridges. Split EHR by data STRUCTURE — longitudinal event-based (OMOP-CDM/MEDS
  → Transformer/GRU) vs aggregated tabular (→ XGBoost); MIMIC/eICU modeled as
  realizable-as-either. 281 nodes / 316 edges (ADR-0028).
- **Reified benchmarks + real ML seeding** — `ml_schema.BenchmarkResult` reifies
  (model, dataset, metric, VALUE, DATE) as a traversable node + `leaderboard()` temporal
  view; `ml_seed.py` fetches REAL authorship/dates from the arXiv API for ~13 seminal
  methods → `seeds/ml_fused.json` (`KG_BACKEND=ml`). Verified: real authorship (ResNet
  He/Sun 2015, ViT Dosovitskiy/Houlsby 2020); GLUE churn RoBERTa 88.5(2019)>BERT 80.5(2018)
  (PR #34 · ADR-0028).
- **Fused ML+biomedical schema** — `ml_schema.py` + `KG_BACKEND=ml_demo`: an ML/method
  layer built around methods being epistemically distinct from phenomena — authorship
  (first/last author, lab), Publication+year, lineage (`derived_from`/`superseded_by`),
  and an edge epistemic class where `achieves`/`outperforms` are LOW-trust (benchmark-
  relative, non-stationary) vs stable `suited_to`/`trained_with`. Bridge = Disease→
  DataModality→Architecture. Verified: cross-domain path (AF→ECG→Transformer), lineage
  (RoBERTa→BERT→Transformer), and the trust split grounds benchmark edges weak. Plugs into
  the existing traversal unchanged (PR #33 · ADR-0027).
- **Pydantic validation on structured output** — `schemas.py` + `llm.parse()`:
  keeps the proven constrained-decoding schema, adds Pydantic validation of the RESULT
  with retry-on-failure (feeds the error back) + code-fence stripping + type coercion.
  All 6 structured-output sites (agent ×4, critic, campaign) hardened. Verified: bad-JSON
  retry, missing-field retry, fenced-reply strip, `"250"`→int. A targeted boundary
  hardening — no framework (LangChain/LangGraph judged overkill) (PR #32 · ADR-0026).
- **Validity gates** — `validity.py`: pre-registered, hypothesis-ORTHOGONAL interim
  checks (cohort integrity, data scale, positive/negative controls) declared in the
  spec's `validity_gates` block. A `halt` gate stops a broken run (marked invalid, not
  "negative"); a `flag` warns. Catches machinery bugs WITHOUT steering the analysis
  (p-hacking safeguard). Verified: H001 all-pass (null-gene FDR check = 0.011); a
  cohort gate halts the `{AD:0}` case (the H002 `AD='AA'` bug); on H002 the data-scale
  gate FLAGGED GSE48350's max=59.24 — a real log-scale anomaly the original run missed.
  Folded into the provenance card (PR #30 · ADR-0024).
- **Campaign / program object** — `campaign.py`: a lineage (DAG) of atomic experiments
  (`campaigns/{name}.json`) where result-driven adaptivity safely lives. Auto-syncs each
  node's verdict from its evaluation report; `next_step()` proposes the NEXT atomic
  experiment from the last verdict + the evaluator's recommendations (LLM-assisted,
  human-approved draft). Verified: H001->H002 lineage; planner proposed H003 (ROSMAP
  snRNA-seq, powered, cell-type-aware) tagged draft/do-not-mutate-H002 (PR #31 · ADR-0025).

## 2026-08-13
- **Scaling profile + `scaling.py`** — content accounting per experiment (bytes/lines/
  tokens + scientific-op count; `python scaling.py` for a cross-experiment table).
  Measured: real-data H002 vs synthetic H001 ≈ 1.8× on-disk (run log 24×) and ~3× Claude
  subagent tokens (~73k→218k), dominated by runner+evaluator. Finding: **generation is
  token-free (local Qwen); testing/interpreting is the paid, dominant half** — cheap to
  propose, expensive to test honestly (PR #29 · ADR-0023).
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
