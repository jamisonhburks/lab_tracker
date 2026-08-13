# ADR-0001: Local Qwen3-14B via Ollama (not a cloud API)

- **Date:** 2026-08-11
- **Status:** Accepted

## Context
The agent reasons over de-identified but still clinical data (EHR, ECG, genomic).
We needed a model to drive the tool-calling loop.

## Options considered
- **Cloud API** (e.g. Anthropic/OpenAI): strongest agentic reliability, but data
  leaves the machine, per-token cost/quota, rate limits.
- **Local open model** (Qwen3-14B via Ollama): on-device, free, offline-capable.

## Decision
Run a **local Qwen3-14B model via Ollama** as the agent's brain.

## Rationale & evidence
- **Privacy** — health data never leaves the machine (the decisive factor).
- **Reproducibility** — a pinnable weights artifact; a run can be reproduced later.
- **Cost / no token quota** — important for an agent that thinks a lot.
- Fits the hardware: 14B at 4-bit ≈ 9 GB on the user's 24 GB M4; MPS benchmark
  confirmed the GPU is usable for local inference.
- Accepted cost: weaker long-horizon agentic reliability than a frontier model —
  mitigated by grounding the model in tools + KG rather than trusting parametrics.

## Consequences
- The whole system is local-first; every later component (KG, embeddings,
  normalization) was chosen to run on-device.
- Compute, not tokens, becomes the bound (see the compute-cluster discussion).
