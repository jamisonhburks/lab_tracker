# toy-research-agent

A fully-local biomedical research agent: a Qwen3-14B model (via Ollama) in a manual
tool-calling loop, grounded in layered memory and a knowledge graph. Built to keep
data on-device and to make every claim provenance-carrying and verifiable.

## What it does

The loop is: call the model → if it requested a tool, run it and feed the result
back → repeat. The model orchestrates ~11 tools across:

- **Literature** — `search_pubmed`; `curate_literature` (scrape → per-paper
  extraction → write structured associations to the agent's own KG).
- **Memory** — episodic (what happened) + semantic (what's true), with hybrid
  retrieval; `recall_past_runs`, `search_semantic`, `query_curated_kg`.
- **Knowledge graph** — `query_graph`, `find_paths` (A→B→C discovery) over
  Hetionet; typed entity normalization (HGNC genes + BioLORD diseases).
- **Hypothesis** — `assess_hypothesis` (degree-weighted realism), `calibrate_link`
  (permutation-null p-value), `propose_experiment` (data/methods/tests).

Every finding is bound to its sources; a guardrail filters provenance to what was
actually retrieved; KG grounding and power-weighted evidence feed a confidence
score. Absence of KG/evidence support is treated as *novel/unverified*, never *false*.

## Setup

```sh
ollama pull qwen3:14b
pip install -r requirements.txt        # sentence-transformers is optional (semantic norm)
export KG_BACKEND=hetionet             # demo | hetionet | optimuskg (default demo)
# optional: export ENTITY_NORM=semantic   # BioLORD disease-synonym normalization
# optional: export LLM_BACKEND=anthropic  # use Claude instead of local Qwen3 (needs `anthropic` + API key)
```

## Run

```sh
python agent.py "How are Crohn's disease and ulcerative colitis connected?"   # single-shot
python agent.py                                                               # persistent REPL (KG stays warm)
```

## Docs & audit trail

- **[`AGENTS.md`](AGENTS.md)** — read first if you're an agent starting or organizing a
  project. Routes to **[`lab-standard/`](lab-standard/)**, the onboarding playbook that
  scaffolds/conforms projects and promotes their work local semantic → shared WIP →
  shared consensus. Run `python scaffold.py new "<title>"` (or `conform <path>`) to
  auto-build a standard-conforming project skeleton.
- **[`docs/decisions/`](docs/decisions/)** — Architecture Decision Records: *why*
  each choice was made, alternatives, and evidence. Start here.
- **[`docs/related-work.md`](docs/related-work.md)** — verified prior-art map + honest
  novelty positioning (what's established vs. a contribution). Every citation fetched-and-checked.
- **[`docs/deployment.md`](docs/deployment.md)** — run one shared substrate for the lab over
  HTTP on your cluster (transport, per-user attribution, locking, TLS/auth, privacy).
- **[`CHANGELOG.md`](CHANGELOG.md)** — reverse-chronological change summary.
- **[`docs/agent-architecture.md`](docs/agent-architecture.md)** — the multi-agent
  target design and build plan.
- **[`docs/kg-schema-spec.md`](docs/kg-schema-spec.md)** — the reified-association
  KG schema.

## Notes

- First run loads the model (~9GB) and the KG (~20s); the REPL pays this once.
- Local by design (privacy for clinical data); bounded by compute, not token quota.
- Expect well-grounded, verifiable hypotheses — not frontier-level creative leaps.
