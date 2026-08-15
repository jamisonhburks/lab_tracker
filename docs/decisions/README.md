# Decision log (ADRs)

Architecture Decision Records — one dated file per significant choice, so a
collaborator (or future you) can audit *why* the system is built the way it is,
what alternatives were weighed, and what evidence backed the call.

Each ADR: **context · options considered · decision · rationale + evidence ·
consequences**. Records are immutable once Accepted; a reversal gets a new ADR
that supersedes the old one (noted in both).

New substantive changes should add an ADR alongside their PR.

| ADR | Decision | Date | Status | PRs |
|---|---|---|---|---|
| [0001](0001-local-model.md) | Local Qwen3-14B via Ollama (not a cloud API) | 2026-08-11 | Accepted | pre-repo |
| [0002](0002-layered-memory-provenance.md) | Layered memory with claim-level provenance | 2026-08-11 | Accepted | pre-repo |
| [0003](0003-retrieval-scorers.md) | Retrieval scorers: recency-decay, hybrid, MMR, threshold | 2026-08-11 | Accepted | pre-repo |
| [0004](0004-hetionet-interim-kg.md) | Hetionet as interim KG; backend-swappable; OptimusKG deferred | 2026-08-12 | Accepted | #2 |
| [0005](0005-hybrid-over-pretraining.md) | Hybrid LLM+KG over pure KG-pretraining | 2026-08-13 | Accepted | — |
| [0006](0006-reified-association-schema.md) | Reified-association schema (Biolink + BFO/IAO) | 2026-08-12 | Accepted | #1, #5 |
| [0007](0007-power-weighted-negative-evidence.md) | Power-weighted negative evidence | 2026-08-12 | Accepted | #6 |
| [0008](0008-kg-as-verifier.md) | KG-as-verifier grounding check (novel ≠ false) | 2026-08-12 | Accepted | #7 |
| [0009](0009-type-aware-normalization.md) | Type-aware entity normalization (HGNC + BioLORD) | 2026-08-13 | Accepted | #10–#12 |
| [0010](0010-permutation-null-calibration.md) | Permutation-null calibration of the realism metric | 2026-08-13 | Accepted | #14 |
| [0011](0011-multi-agent-architecture.md) | Orchestrator + specialists; separation of concerns | 2026-08-13 | Accepted | #8, #9 |
| [0012](0012-git-workflow.md) | Git workflow: private, no co-author, small PRs | 2026-08-12 | Accepted | all |
| [0013](0013-critic-agent.md) | Critic agent + test-driven evaluation | 2026-08-13 | Accepted | #17, #18 |
| [0014](0014-llm-adapter.md) | LLM provider adapter (Ollama ↔ Claude swappable) | 2026-08-13 | Accepted | #19 |
| [0015](0015-novelty-and-hybrid-generation.md) | Novelty flag + hybrid (KG-constrained) generation | 2026-08-13 | Accepted | #21 |
| [0016](0016-refinement-loop.md) | Refinement loop: novelty-filtered curate+critic triage | 2026-08-13 | Accepted | #22 |
| [0017](0017-monarch-kg-backend.md) | Monarch KG backend (larger, named, phenotype-rich) | 2026-08-13 | Accepted | #23 |
| [0018](0018-combined-kg.md) | Combined KG (Hetionet + Monarch) — local PrimeKG slice | 2026-08-13 | Accepted | #23 |
| [0019](0019-claude-specialist-skills.md) | Claude specialist for scientific tool use (Agent Skills) | 2026-08-13 | Accepted | #24 |
| [0020](0020-closed-scientific-loop.md) | Close the scientific loop (generate → test → evaluate) | 2026-08-13 | Accepted | #25 |
| [0021](0021-tool-ledger.md) | Per-run tool ledger (intended vs actual tool use) | 2026-08-13 | Accepted | #27 |
| [0022](0022-provenance-view.md) | Unified per-experiment provenance view | 2026-08-13 | Accepted | #28 |
| [0023](0023-scaling-profile.md) | Scaling profile — content per hypothesis, `scaling.py` | 2026-08-13 | Accepted | #29 |
| [0024](0024-validity-gates.md) | Pre-registered validity gates (interim, hypothesis-orthogonal) | 2026-08-14 | Accepted | #30 |
| [0025](0025-campaign-program.md) | Campaign/program object — experiment lineage + planner | 2026-08-14 | Accepted | #31 |
| [0026](0026-pydantic-validation.md) | Pydantic validation + retry on the structured-output boundary | 2026-08-14 | Accepted | #32 |
| [0027](0027-fused-ml-schema.md) | Fused ML+biomedical schema — methods as a distinct epistemic class | 2026-08-14 | Accepted | #33 |
| [0028](0028-reified-benchmarks-real-seed.md) | Reified benchmark results + real arXiv seeding | 2026-08-14 | Accepted | #34 |
| [0029](0029-kg-grounded-method-selection.md) | KG-grounded ML method selection (Stage 3) | 2026-08-14 | Accepted | #36 |
| [0030](0030-mcp-substrate-server.md) | MCP substrate server — expose the substrate to external sessions | 2026-08-14 | Accepted | #37 |
| [0031](0031-substrate-scoping-wip.md) | Three-tier substrate scoping (personal / shared-WIP / consensus) | 2026-08-14 | Accepted | #38 |
| [0032](0032-contribute-pipeline.md) | `contribute()` write-path into shared consensus (critic-gated, attributed) | 2026-08-14 | Accepted | #39 |
| [0033](0033-lab-standard-onboarding-playbook.md) | Lab-standard onboarding playbook — self-describing repo → conforming projects | 2026-08-14 | Accepted | #40 |
| [0034](0034-scaffold-helper.md) | `scaffold.py` — automate the mechanical half of onboarding | 2026-08-14 | Accepted | #41 |
| [0035](0035-resilient-live-retrieval.md) | Resilient live retrieval (`net.py`, tenacity-optional) | 2026-08-14 | Accepted | #42 |
| [0036](0036-ml-bridge-stage2.md) | ML bridge breadth (Stage 2) — disease↔modality↔task↔architecture coverage | 2026-08-14 | Accepted | #43 |
| [0037](0037-ml-bulk-ingestion.md) | Bulk method ingestion (Stage 4) — `ml_ingest.py` + `ml_full` backend | 2026-08-14 | Accepted | #44 |
| [0038](0038-idea-intake-followup.md) | Idea intake — `assess_idea` (evaluate → propose → opt-in refine) | 2026-08-14 | Accepted | #45 |
| [0039](0039-mesh-hpo-symptom-merge.md) | MeSH↔HPO symptom/phenotype merge in the combined KG | 2026-08-14 | Accepted | #46 |
| [0040](0040-thinker-supplied-critic.md) | Thinker-supplied critic verdict — Claude gates consensus, substrate stays LLM-free | 2026-08-14 | Accepted | #47 |
| [0041](0041-session-journal.md) | Session journal — keep the personal tier alive during a live session | 2026-08-14 | Accepted | #48 |
| [0042](0042-synthesize-on-compact.md) | Synthesize-before-clear/compact (Claude Code hooks) | 2026-08-14 | Accepted | #49 |
| [0043](0043-exploratory-lane.md) | The exploratory lane — ad-hoc analyses, misc findings, match + group | 2026-08-14 | Accepted | #50 |
| [0044](0044-semantic-grouping-formalize.md) | Semantic grouping (synonyms cluster) + one-step cluster→hypothesis | 2026-08-14 | Accepted | #51 |
| [0045](0045-http-deployment.md) | Remote/HTTP MCP deployment — one shared substrate on the cluster | 2026-08-15 | Accepted | #53 |
| [0046](0046-deep-search-distillation-cache.md) | Deep-search distillation → primary KG (cache expensive sweeps) | 2026-08-15 | Accepted | #54 |
| [0047](0047-deep-search-cache-maturation.md) | Mature the deep-search cache — expiry, graduation, curate integration | 2026-08-15 | Accepted | #55 |
| [0048](0048-refresh-and-source-independence.md) | Scheduled cache refresh + source-independence for graduation | 2026-08-15 | Accepted | #56 |
| [0049](0049-warm-start-briefing.md) | Warm-start briefing — the enjoyable front door | 2026-08-15 | Accepted | #57 |
| [0050](0050-serendipity-nudges.md) | Serendipity nudges — surprising, relevant connections | 2026-08-15 | Accepted | #58 |
| [0051](0051-research-story.md) | Research story — an honest narrative (caveats + how to solidify) | 2026-08-15 | Accepted | #59 |
| [0052](0052-assistant-not-twin.md) | Assistant, not twin — personalize to the work, not the person | 2026-08-15 | Accepted | #60 |
