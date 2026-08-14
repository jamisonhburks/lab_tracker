# Related Work & Novelty Positioning (verified)

**Purpose.** An honest, citation-checked map of prior art vs. what (if anything) here is a
contribution — so a future session, co-author, or reviewer starts from the verified framing
instead of re-deriving it, and so we never claim as novel what is already established.

**Provenance.** Compiled 2026-08-14 from a multi-agent literature/GitHub sweep, then a second
**verification pass** that fetched each source from an independent host (Crossref, Nature/OUP,
NCBI PMC, Amazon Science, the GitHub API). **Every source below is real** — none were
hallucinated. Caveat: one verifier found the sandbox `export.arxiv.org` API returned mocked
results (rewrote timestamps, "resolved" invented IDs), so "the arXiv id resolves" is *not* proof
on its own; the statuses here rely on independent-host corroboration. **Resolve each DOI once
from a clean network before a final bibliography.**

---

## TL;DR positioning

This system is a **novel integration and architectural stance, not a set of novel components.**
Nearly every mechanism is established prior art, several famously. After verification the novelty
squeeze *tightened*: the "shared governed substrate over MCP" now has a real, near-exact
**domain-agnostic twin** (caura/MemClaw), and the "local-LLM biomedical KG over MCP" has a strong
twin (BioRouter/SPOKEAgent, from the *same lab* whose calibration method we reuse). What survives:

1. **Strongest standalone claim — the fused biomedical + ML-methods KG for method selection by
   traversal** (`method_select`): no verified prior work fuses an ML-methods KG onto a biomedical
   KG to recommend *architectures* by a symbolic path (disease → modality → architecture → task →
   loss → metric → caveat), with methods carrying authorship/lineage.
2. **The specific union** — a biomedical hypothesis *thinker* that writes *permutation-calibrated,
   novelty-checked, power-weighted* findings back into a **critic-gated, conclusion-vs-process
   tiered** shared KG. No single source assembles this, but every *piece* now has a named owner →
   publishable only as a **systems-integration contribution behind real evaluation**, not a new
   mechanism.

Realistic venues: AI-for-Science / ML4H / agents workshops, or a systems/demo/reproducibility
track. Claim (1) could be carved out for a methods/bioinformatics submission.

---

## A. Foundations we build on — cite as prior art, do NOT claim as novel

| Our component | Canonical prior work | id / DOI |
|---|---|---|
| A→B→C bridge paths (`find_paths`) | Swanson, "Fish oil, Raynaud's syndrome, and undiscovered public knowledge," *Persp. Biol. Med.* 30(1):7–18 (1986) — literature-based discovery | 10.1353/pbm.1986.0087 |
| DWPC + degree-preserving permutation null (`calibrate_link`) | Himmelstein, … Baranzini, "Systematic integration of biomedical knowledge prioritizes drugs for repurposing," *eLife* 6:e26726 (2017) — Hetionet/Rephetio | eLife 26726 |
| Novelty vs literature (`check_novelty`) | Wang, Downey, Ji, Hope, "SciMON: Scientific Inspiration Machines Optimized for Novelty," **ACL 2024** | arXiv:2305.14259 |
| KG-grounding LLM claims (`ground_claim`) | GraphRAG (Edge et al.); Think-on-Graph (Sun et al., **ICLR 2024**); MedGraphRAG (Wu et al.); KRAGEN (Matsumoto et al., *Bioinformatics* 40(6):btae353) | 2404.16130; **2307.07697**; 2408.04187; btae353 |

> Do not present any of these as a contribution — it would be a re-implementation and would not
> survive review. `calibrate_link` in particular *is* Rephetio; reviewers cite Himmelstein 2017 on
> sight.

---

## B. Closest system twins — differentiate hard

### Substrate / governed shared memory (this got *more* threatening after verification)
| System | What it is | Overlap / the delta |
|---|---|---|
| **caura / MemClaw** — repo `caura-ai/caura` (formerly `caura-memclaw`, Apache 2.0, ~430★); paper "Governed Shared Memory for Multi-Agent LLM Systems," arXiv:2606.24535 | MCP-native governed shared memory: **trust tiers, provenance/audit, knowledge graph, self-improving retrieval**, statuses pending→confirmed→outdated→conflicted | **Near-exact twin of our substrate governance**, but domain-agnostic (agent-fleet infra). No biomedical grounding, no permutation-null/novelty, no hypothesis loop. Cite as `caura-ai/caura`. |
| **Graphiti** — `getzep/graphiti` (~30k★) | Temporal KG for agents; **MCP server + dense+BM25+graph hybrid retrieval**; Ollama | **Our exact retrieval stack + MCP already exists here.** Lacks tiered personal→WIP→consensus promotion, critic gate, biomedical focus. |
| **Meko** (Yugabyte) | Agent memory: per-agent private + shared "Collective Memory," hot/cold tiering | Three-tier + private→shared promotion — but **promotion is human-gated/manual** per the authoritative blog (vendor messaging inconsistent; don't call it automatic). |
| **Collaborative Memory** — Rezazadeh et al., arXiv:2505.18279 | Two-tier private/shared memory + dynamic access control + **immutable provenance** | Strong precedent for our tiering + provenance; no critic gate, no consensus accrual. |

### Biomedical KG over MCP (strong twin — same lab as our calibration method)
| System | What it is | Delta |
|---|---|---|
| **BioRouter** — `BaranziniLab/biorouter` (UCSF) | Local-LLM biomedical research platform; **MCP** ecosystem; personal KBs; queries SPOKE | Most feature-overlapping biomedical system. Unclear on gated write-back / promotion tiers / permutation calibration. |
| **SPOKEAgent** — `BaranziniLab/SPOKEAgent` | MCP server over the ~43M-node **SPOKE** biomedical KG; path-finding | **Read-only** ("write operations not permitted") — our critic-gated write-back is the delta. |
| **mcp-proto-okn** — Rose, Su, Baranzini, arXiv:2605.30283 (repo `sbl-sdsc/mcp-proto-okn`); **MCPmed** — Flotho et al., *Brief. Bioinform.* 2026 (10.1093/bib/bbag076; arXiv:2507.08055) | MCP → SPARQL/query over open scientific KGs; a *call* for MCP-enabled bioinformatics services | "Expose a biomedical KG over MCP for LLMs" is now a **named, emerging pattern** — undercuts MCP-exposure as novelty. |

### Automated hypothesis-generation / "AI scientist" systems
| System | id | Note vs us |
|---|---|---|
| Google **AI co-scientist** — Gottweis, Weng et al. (2025) | arXiv:2502.18864 | Multi-agent Gemini, **Elo tournament** ranking. LLM-in-the-loop; no LLM-free substrate, no permutation null, single-session (no multi-user accrual). |
| **SciAgents** — Ghafarollahi & Buehler | arXiv:2409.05556; *Adv. Mater.* 37(22):2413523 (2025) | Closest KG-traversal hypothesis gen — but the graph layer is **LLM-driven** (no statistical scoring). Materials, not biomedical. |
| **Robin** + **PaperQA2** — FutureHouse | 2505.13400; 2409.13740 (title: "Language agents achieve superhuman synthesis of scientific knowledge") | Robin: multi-agent bio discovery (dry-AMD/ripasudil). PaperQA2 ≈ our grounding/provenance — weakens novelty there. Cloud frontier models. |
| **ResearchAgent** — Baek et al. (KAIST–Microsoft) | arXiv:2404.07738 | Iterative idea gen + reviewing agents over an academic graph; no substrate/null/tiers. |
| **AgentRxiv** — Schmidgall & Moor (2025) | arXiv:2503.18102 | **The multi-user analogue.** Shared agent-lab reports, retrieved by similarity, **with no review step** (the paper does *not* say "append-only/immutable" — that's our inference; keep the *no-gate* contrast, drop the word). Our gated/tiered promotion is the explicit response. |
| Sakana **AI Scientist** v1/v2 | 2408.06292 / **2504.08066** | End-to-end automated ML papers; no KG substrate, no biomedical grounding. |
| **Agent Laboratory** (2501.04227); **Coscientist** — Boiko, MacKnight, **Kline**, Gomes, *Nature* 624:570–578 (2023); **HypoGeniC** paper "Literature Meets Data" (2410.17309) | — | Adjacent; none combine a gated shared biomedical KG substrate with permutation calibration. |

---

## C. Method-selection KG prior art (for Claim 1, the fused bio+ML KG)

| Prior work | id / DOI | Why it's *not* us |
|---|---|---|
| **AI-KG** — Dessì et al., ISWC 2020 | 10.1007/978-3-030-62466-8_9 | ML-research-entity KG; standalone (no biomedical fusion, no method-for-problem selection). |
| **CS-KG 2.0** — Dessì et al., ISWC 2022 / *Sci Data* 2025 | 10.1007/978-3-031-19433-7_39; 10.1038/s41597-025-05200-8 | ~350M-triple CS KG with Method entities; no biomedical fusion. |
| **ITO** — Blagec et al., *Sci Data* 2022 | 10.1038/s41597-022-01435-x | Tasks↔datasets↔metrics↔models KG — the nearest "task→metric" spine; no disease/modality entry, no lineage. |
| **KGmetaSP** — Klironomos et al. | arXiv:2603.19888 | Method recommendation for a dataset — but via **embeddings/meta-features over OpenML**, not symbolic traversal, no biomedical grounding. |

**Verified gap:** none fuses an ML-methods KG onto a biomedical KG so that the *recommended node
is the ML architecture*, reachable by traversal, with `derived_from`/`superseded_by` lineage.
Distinctiveness ≈ 7/10 (combinatorial: every ingredient is off-the-shelf; the fusion is not).

---

## D. Governance / novelty precedents

| Prior work | id | Relation |
|---|---|---|
| "Closing the Feedback Loop … Insight Governance in Verbal RL" — Cui et al. (ICML 2026 workshop) | arXiv:2606.17591 | **Append-only per-rule evidence log** — closest structural precedent for our contribution ledger; single-agent, financial. |
| "An Axiomatic Benchmark for Evaluation of Scientific Novelty Metrics" — Liu & Zhai | arXiv:2604.15145 | How to *evaluate* a novelty metric — relevant if we defend `check_novelty`. |
| Wikidata for the life sciences (Waagmeester et al., *eLife* 2020); WikiPathways; nanopublications | — | Bot/human-gated community curation with provenance — precedent for critic-gate + conservative routing (no confidence-projection-over-contributors, no process/conclusion tiering). |

---

## E. Prior-art vs contribution — the explicit call

| Claim | Verdict |
|---|---|
| A→B→C / LBD | **Prior art** (Swanson). Drop. |
| DWPC + permutation null | **Prior art** (Rephetio). Drop. |
| KG-grounding / Graph-RAG | **Prior art** (GraphRAG/ToG/MedGraphRAG/KRAGEN). Drop. |
| Novelty via co-mention | **Prior art** (SciMON). Drop. |
| Local/frozen LLM, no RL | Commodity deployment decision. Drop as a novelty claim. |
| MCP-exposed biomedical KG | **Emerging named pattern** (SPOKEAgent, mcp-proto-okn, MCPmed, BioRouter). Drop. |
| Shared governed memory w/ tiers + provenance over MCP | **Twin exists** (caura/MemClaw; Graphiti; Meko; Collaborative Memory). Do not claim the mechanism. |
| **Fused bio + ML-methods KG, method selection by traversal** | **Under-occupied** — Claim 1. Keep, behind evaluation. |
| **LLM-free substrate + swappable/frozen thinker (judgment lives outside the model)** | Architectural **stance**, under-explored vs the LLM-in-the-loop field. Keep as framing. |
| **Critic-gated, conclusion-vs-process 3-tier consensus for a research lab** | The **conclusion-vs-process tiering** has no clear precedent; the gate itself rhymes with Wikidata + the 2026 verbal-RL ledger. Keep the *tiering policy* as the contribution. |
| **Power-weighted, negative-evidence-aware confidence inside the hypothesis-scoring loop** | Statistics are textbook (Altman–Bland, TOST, Bayes factors); no prior found *wiring it into automated hypothesis confidence*. Best narrow novelty — claim precisely. |

---

## F. If we want it publishable — evaluation to run (framing won't survive review alone)

1. **Governance ablation:** gated/tiered promotion vs. ungated AgentRxiv-style sharing — does gating reduce propagated hallucinated findings?
2. **Confidence ablation:** power-weighted negative-evidence vs. naive "null = refuted" — does it change hypothesis rankings?
3. **Method-selection:** KG traversal vs. a meta-learning recommender baseline (e.g., KGmetaSP-style).
4. **Baseline against the twins:** caura/MemClaw (governance), Graphiti (retrieval), BioRouter/SPOKEAgent (biomedical MCP-KG) — show what the *union* adds.

---

*Maintenance: when adding a capability, check it here first; if it maps to a row above, it's an
integration, not a contribution — say so in its ADR.*
