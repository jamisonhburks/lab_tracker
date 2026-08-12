# Multi-agent architecture — design

Status: **design note.** Captures the target system this project grows into. Today
we have the *orchestrator* ("brain") plus one literature tentacle and the
KG/memory substrate; this doc lays out the specialist agents it will deploy and
the rules that keep them honest.

---

## 1. The shape: orchestrator + specialists

The current `agent.py` loop is the **brain** — it synthesizes information, deploys
paper search, generates and scores hypotheses. A full research system is that
brain **deploying other classes of agents** it can call, each a specialist with
its own prompt, tools, and (optionally) model size. This is the architecture of
the autonomous-discovery systems: Google *AI co-scientist*, Sakana *AI Scientist*,
*SciAgents*, *ResearchAgent*.

Each specialist is just **another tool-loop** (same pattern as `agent.py`). The
brain deploys them via a `spawn_agent`-style tool or a workflow. They share one
substrate — episodic + semantic memory + the KG + the provenance discipline — so a
finding scraped by one, curated by another, and tested by a third carries its
sources the whole way.

---

## 2. Agent classes

| Class | Job | Status | Runs on |
|---|---|---|---|
| **Orchestrator ("brain")** | Decompose the question, deploy specialists, generate + score hypotheses, synthesize | ✅ `agent.py` + hypothesis tools | reasoning LLM |
| **Paper scraper** | Fetch papers (PubMed / arXiv / bioRxiv, full text) | 🟡 `search_pubmed` (abstracts only) | cheap LLM + I/O |
| **Synthesizer / extractor** | Read many papers → **structured** findings (claim, effect size, N, power, method, dataset) | ⬜ | LLM |
| **KG curator** | Write extracted associations *into* the KG with provenance + epistemic type | ⬜ | code + LLM |
| **Critic / adversarial verifier** | Attack each hypothesis; kill the weak ones | ⬜ | LLM |
| **Experiment designer** | Hypothesis → concrete protocol | 🟡 `propose_experiment` | LLM |
| **Dataset / method finder** | Locate the right data (UK Biobank, GEO, dbGaP) + method | ⬜ | tools |
| **Implementer** | Write the analysis code | ⬜ (= CLAUDE.md `code-implementer`) | LLM |
| **Runner** | Execute on data/compute — GWAS, model training, power calc | ⬜ (= `experiment-runner`) | **compute cluster** |
| **Evaluator** | Interpret results vs. hypothesis + stats standards | ⬜ (= `results-evaluator`) | LLM |

These mirror the roles already declared in the project's global `CLAUDE.md`
(hypothesis-planner, experiment-runner, results-evaluator, lit-biomedical,
lit-ml-architecture, code-implementer) — this is the local, in-agent expression of
that division of labor.

---

## 3. The load-bearing rule: separate generate / execute / interpret

The single most important design constraint, and it's already in `CLAUDE.md`:

> *"experiment-runner executes; it does not interpret. results-evaluator interprets;
> it does not re-run. hypothesis-planner approves before any code is written."*

Keeping these as **separate agents** prevents the failure that kills naive research
agents: **self-confirmation.** One agent that generates a hypothesis, runs the test,
*and* judges the result will rationalize its own hypothesis into "confirmed."
Splitting the roles — a generator that proposes, a runner that executes blindly, an
evaluator that judges without a stake in success, a critic that actively attacks —
is the multi-agent analog of the hallucination guardrails already built (provenance,
KG grounding, power-weighted evidence). **It is adversarial by construction.**

---

## 4. The discovery loop

```
question
  → brain decomposes
  → [scraper → synthesizer → KG curator]        gather evidence, grow the KG
  → brain generates hypotheses;                 score realism / grounding / confidence
  → critic attacks;                             survivors advance
  → experiment designer + dataset/method finder plan the test
  → implementer → runner → evaluator            run it (blindly) and judge it
  → results feed back → brain refines or accepts
```

Shared substrate flows across every arrow: **memory (episodic + semantic), the KG,
and provenance** — including the negative-evidence fields (`power`, `direction`,
`sample_size`) so a scraped null carries its power into the confidence scorer.

---

## 5. Local + compute mapping

Not all agents cost the same — which is where a compute cluster actually matters:

- **Cheap / small-model:** scraper, KG curator (mostly I/O + extraction).
- **Reasoning-heavy:** brain, critic, evaluator (14B locally, or 70B on a cluster).
- **Compute-heavy:** the **runner** — the only class that truly needs the cluster
  (running a GWAS, training a model, computing power for a re-test). The brain is
  cheap; the *execution* is where GPU-hours go.

Self-hosting removes the token-quota ceiling (good for a brain that thinks a lot);
a cluster adds bigger models, concurrency, the persistent-KG service, and the
compute the runner needs. You trade a token budget for GPU throughput.

---

## 6. Prior art & honest caveats

**Prior art:** AI co-scientist (Google, 2025), The AI Scientist (Sakana, 2024),
SciAgents (Buehler, 2025), ResearchAgent (Baek, 2025), KG-CoI (Xiong, 2024, for the
KG-grounded hallucination check we implemented).

**Caveats:**
- The **literature + hypothesis** half is mature; **autonomous execution**
  (implementer → runner → evaluator on real data) is the hard, less-proven half —
  especially with clinical data and this project's reproducibility/stats standards.
  Expect a **human in the loop** at the execute/interpret boundary for now.
- **Coordination overhead is real:** more agents = more failure modes and harder
  debugging. Add one specialist at a time and verify each handoff before the next.
- Don't build all ten. The value compounds only if each agent's output is
  provenance-carrying and consumable by the next.

---

## 7. Build order (each a small PR)

Dependency-ordered; earliest first:

1. **Synthesizer/extractor → KG curator** — highest leverage. Reads papers into
   structured associations (with the §evidence fields) and writes them to the
   agent's *own* KG. Simultaneously grows the KG the brain grounds on, populates
   the evidence the confidence scorer needs, and realizes "the agent's own written
   ontological memory." Depends on the reified `Association`/`Evidence` schema.
2. **Critic** — cheapest standalone hallucination win; no new data plumbing.
3. **Spawn/orchestration primitive** — a `spawn_agent` tool so the brain deploys
   specialists explicitly (vs. one flat tool list).
4. **Experiment designer → dataset/method finder** — extends `propose_experiment`
   toward concrete, data-grounded protocols.
5. **Implementer → runner → evaluator** — the execution half; needs the compute
   cluster and a human-in-the-loop gate. Build last, behind the separation-of-
   concerns rule (§3).

---

## 8. Current status

- ✅ Brain: `agent.py` tool-loop (local Qwen3-14B via Ollama)
- ✅ Memory substrate: working / episodic / semantic (hybrid retrieval scorers)
- ✅ KG (read-only grounding): Hetionet, swappable backends; traversal, paths
- ✅ Hypothesis tooling: realism (degree-weighted), experiment sketch, KG grounding
  check, power-weighted confidence with negative-evidence handling
- 🟡 Literature: abstract search only (no full-text, no structured extraction)
- ⬜ Everything in §2 marked ⬜ — the specialist agents this doc plans
