# Changelog

Reverse-chronological summary of substantive changes. Each entry links a PR to the
decision behind it (see `docs/decisions/`). Dates are approximate build dates.

## 2026-08-13
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
