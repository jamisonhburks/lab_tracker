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
| [0013](0013-critic-agent.md) | Critic agent + test-driven evaluation | 2026-08-13 | Accepted | #17 |
