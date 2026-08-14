"""mcp_server — the lab substrate exposed over MCP (local stdio).

This makes the substrate ACCESSIBLE and AUDITABLE from outside the local agent loop:
a fresh Claude session (Claude Desktop / Claude Code / any MCP client) connects and can
GROUND its own thinking against the KG, check NOVELTY, CALIBRATE a link against chance,
recall PRIOR work (incl. negative results), read CURATED findings with confidence, pick
METHODS by traversal, and AUDIT experiment provenance.

Design principle (substrate, not thinker): this server contains NO LLM. It only exposes
what an external thinker can't do itself — grounding, calibration, novelty-vs-chance,
lab memory, provenance — never generation or generic web search. Every tool returns the
EVIDENCE (paths, PMIDs, confidence, why), so the thinker can *check*, not just trust.
Tool results flow back to the client's model, so tools emit associations / grounding /
aggregates — never row-level patient data.

Run (local stdio):   python mcp_server.py
KG backend:          set KG_BACKEND (demo | hetionet | monarch | combined | ml) before launch.

Register with a client:
  Claude Desktop — add to claude_desktop_config.json:
    {"mcpServers": {"lab-substrate": {"command": "python",
       "args": ["/ABS/PATH/toy-research-agent/mcp_server.py"],
       "env": {"KG_BACKEND": "combined"}}}}
  Claude Code — claude mcp add lab-substrate -- python /ABS/PATH/mcp_server.py
"""

import json
import os
from pathlib import Path

from fastmcp import FastMCP

import kg_memory as kg
import hypothesis_tools as hyp
import novelty
import memory
import kg_writer
import confidence

try:                                  # method selection lands with Stage 3 (PR #36)
    import method_select
except ImportError:
    method_select = None

ROOT = Path(__file__).parent
mcp = FastMCP("lab-substrate")


# --------------------------------------------------------------------------- #
# Tools — the substrate's queries. Each returns evidence, not just an answer.  #
# --------------------------------------------------------------------------- #

@mcp.tool
def ground_claim(subject: str, object: str) -> str:
    """Grade how well a TRUSTWORTHY knowledge-graph subgraph corroborates a claimed link
    between two entities: grounded | weakly_grounded | novel_unverified | off_graph.
    Absence of support is NOT falsity (the KG is incomplete) — 'novel' means verify, not
    reject. Use to separate a grounded claim from a plausible-sounding guess."""
    return kg.check_connection(subject, object)


@mcp.tool
def find_paths(entity_a: str, entity_c: str, max_hops: int = 3) -> str:
    """Find connecting paths A->B->C between two entities in the knowledge graph, each with
    its source — the mechanistic-link evidence behind a hypothesis (e.g. a shared gene)."""
    return kg.find_paths(entity_a, entity_c, max_len=max_hops)


@mcp.tool
def query_kg(entity: str) -> str:
    """Return an entity's typed neighbors in the knowledge graph, each with its source."""
    return kg.query_graph(entity)


@mcp.tool
def assess_hypothesis(entity_a: str, entity_c: str) -> str:
    """Score how well the KG supports a hypothesized link (degree-weighted path realism) —
    a heuristic, comparative signal, explicitly not a calibrated probability."""
    return hyp.assess_hypothesis(entity_a, entity_c)


@mcp.tool
def calibrate_link(entity_a: str, entity_c: str) -> str:
    """Calibrate a link against a DEGREE-PRESERVING permutation null: is this pair's
    connection stronger than random pairs of the same degree? Returns a percentile /
    empirical p-value, exposing whether a high score is real signal or hub/density
    inflation. This is the honesty check a fresh session can't do itself."""
    return hyp.calibrate_link(entity_a, entity_c)


@mcp.tool
def check_novelty(entity_a: str, entity_c: str, via: str = "") -> str:
    """Is a link already PUBLISHED or a genuinely new juxtaposition? Asks PubMed whether
    A, C (and an optional bridge `via`) are already co-mentioned. Distinguishes
    rediscovery from a candidate new hypothesis. Novelty != correctness — a reason to
    verify, not to trust."""
    return novelty.check_novelty(entity_a, entity_c, via)


@mcp.tool
def query_curated_findings(subject: str = "", object: str = "") -> str:
    """Read the lab's OWN curated findings (extracted from literature + experiments), each
    with a power-weighted confidence, evidence count, and KG grounding. Check here for what
    the lab has already established / contested / refuted before proposing it anew."""
    recs = kg_writer.query(subject or None, object or None)
    if not recs:
        return "No curated findings match (the curated KG may be empty)."
    lines = []
    for r in recs[:15]:
        grounding = kg.check_connection(r["subject"], r["object"])
        result = confidence.score_association(
            kg_writer.to_association(r), prior=confidence.grounding_prior(grounding))
        lines.append(f"{r['subject']} —{r['predicate']}→ {r['object']}  "
                     f"[{result.status}, conf {result.confidence:.2f}, "
                     f"{len(r['evidence'])} evidence, KG:{grounding}]")
    return "\n".join(lines)


@mcp.tool
def recall_prior_work(query: str, max_results: int = 3) -> str:
    """Consult the lab's EPISODIC memory: has this been investigated before, and what was
    concluded (including negative results)? Build on prior work instead of repeating it."""
    return memory.recall_past_runs(query, max_results)


if method_select is not None:
    @mcp.tool
    def recommend_methods(target: str) -> str:
        """KG-grounded ML method selection: given a data modality (e.g. 'ECG', 'longitudinal
        event-based EHR') or a disease, traverse the fused ML graph for suited architectures
        (with authorship), losses, metrics, and caveats — a graph query, not a lookup."""
        return method_select.recommend_methods(target)


@mcp.tool
def propose_experiment(entity_a: str, entity_c: str, hypothesis: str = "") -> str:
    """Infer the data, study design, statistical tests (Bonferroni + BH, effect sizes,
    power) AND KG-grounded ML methods needed to test a hypothesized link."""
    return hyp.propose_experiment(entity_a, entity_c, hypothesis)


# --------------------------------------------------------------------------- #
# Resources — the audit surface. A thinker reads these to interrogate results. #
# --------------------------------------------------------------------------- #

@mcp.resource("substrate://index")
def index() -> str:
    """What's available to query/audit: experiments, hypotheses, campaigns, KG backend."""
    exps = sorted(p.name for p in (ROOT / "experiments").glob("H*") if p.is_dir())
    hyps = sorted(p.name for p in (ROOT / "hypotheses").glob("*.y*ml"))
    camps = sorted(p.stem for p in (ROOT / "campaigns").glob("*.json")) \
        if (ROOT / "campaigns").exists() else []
    return json.dumps({"kg_backend": os.environ.get("KG_BACKEND", "demo"),
                       "experiments": exps, "hypotheses": hyps, "campaigns": camps},
                      indent=2)


def _read(path: Path, what: str) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else f"No {what} found."


@mcp.resource("provenance://{exp_id}")
def provenance(exp_id: str) -> str:
    """How an experiment was formed AND tested (deterministic provenance card)."""
    return _read(ROOT / "experiments" / exp_id / "provenance.md", f"provenance for {exp_id}")


@mcp.resource("report://{exp_id}")
def report(exp_id: str) -> str:
    """The results-evaluator's interpretation + verdict for an experiment."""
    return _read(ROOT / "reports" / f"{exp_id}_evaluation.md", f"report for {exp_id}")


@mcp.resource("ledger://{exp_id}")
def ledger(exp_id: str) -> str:
    """The ordered scientific-tool trace an experiment actually ran."""
    return _read(ROOT / "experiments" / exp_id / "tool_ledger.json", f"ledger for {exp_id}")


@mcp.resource("hypothesis://{hyp_file}")
def hypothesis(hyp_file: str) -> str:
    """A pre-registered hypothesis spec (question, H0/H1, method, success metric)."""
    hits = list((ROOT / "hypotheses").glob(f"{hyp_file}*"))
    return _read(hits[0], f"hypothesis {hyp_file}") if hits else f"No hypothesis {hyp_file}."


if __name__ == "__main__":
    mcp.run()   # stdio transport (default)
