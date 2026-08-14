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
