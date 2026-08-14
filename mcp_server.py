"""mcp_server — the lab substrate exposed over MCP, in THREE tiers.

Makes the substrate accessible + auditable from outside the agent loop, so a fresh Claude
session can think WITH it. The distinction that matters is CONCLUSION vs PROCESS:

  - PERSONAL (local, private): working memory, in-progress semantic distillations, ad-hoc
    runs — your unfinished thinking. Never shared until it earns its way through contribute().
  - SHARED WIP ("group semantics"): the research PROCESS — experiments, hypotheses,
    campaigns, provenance, tool ledgers, VALIDITY GATES — status-tagged and provisional,
    logged centrally even before a conclusion, so the group can see what's in-flight and
    not duplicate it. No critic gate; it's visibly "in progress".
  - SHARED CONSENSUS: curated findings with confidence — what the lab believes. This is
    the only tier behind the critic-gated contribute() pipeline.

`SUBSTRATE_SCOPE` selects which tiers this instance serves:  personal | shared | all (default).
Run TWO deployments: a `shared` one over the git-repo KG (hosted for the lab) and a
`personal` one over your local episodic + semantic (only your session sees it).

Design: NO generation inside — the thinker is the client's model; this only exposes what
that thinker can't do itself. Tools emit associations / grounding / aggregates, never
row-level patient data.

Run:  SUBSTRATE_SCOPE=shared KG_BACKEND=combined python mcp_server.py
Client (Claude Desktop) — add to claude_desktop_config.json:
  {"mcpServers": {"lab-shared": {"command": "python",
     "args": ["/ABS/PATH/mcp_server.py"], "env": {"SUBSTRATE_SCOPE":"shared","KG_BACKEND":"combined"}},
                  "my-personal": {"command": "python",
     "args": ["/ABS/PATH/mcp_server.py"], "env": {"SUBSTRATE_SCOPE":"personal"}}}}
"""

import glob
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
import contribute as contrib

try:                                  # method selection lands with Stage 3
    import method_select
except ImportError:
    method_select = None

ROOT = Path(__file__).parent
SCOPE = os.environ.get("SUBSTRATE_SCOPE", "all").lower()     # personal | shared | all
_SHARED = SCOPE in ("shared", "all")
_PERSONAL = SCOPE in ("personal", "all")

mcp = FastMCP(f"lab-substrate ({SCOPE})")


def _read(path: Path, what: str) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else f"No {what} found."


# =========================================================================== #
# SHARED tiers: consensus KG/findings (query) + WIP process (group semantics)  #
# =========================================================================== #
if _SHARED:

    @mcp.tool
    def ground_claim(subject: str, object: str) -> str:
        """Grade how well a TRUSTWORTHY KG subgraph corroborates a claimed link:
        grounded | weakly_grounded | novel_unverified | off_graph. Absence of support is
        NOT falsity (the KG is incomplete). Separates a grounded claim from a plausible guess."""
        return kg.check_connection(subject, object)

    @mcp.tool
    def find_paths(entity_a: str, entity_c: str, max_hops: int = 3) -> str:
        """Find connecting A->B->C paths between two entities, each with its source — the
        mechanistic-link evidence behind a hypothesis (e.g. a shared gene)."""
        return kg.find_paths(entity_a, entity_c, max_len=max_hops)

    @mcp.tool
    def query_kg(entity: str) -> str:
        """An entity's typed neighbors in the knowledge graph, each with its source."""
        return kg.query_graph(entity)

    @mcp.tool
    def assess_hypothesis(entity_a: str, entity_c: str) -> str:
        """Degree-weighted path realism for a hypothesized link — heuristic, comparative,
        explicitly not a calibrated probability."""
        return hyp.assess_hypothesis(entity_a, entity_c)

    @mcp.tool
    def calibrate_link(entity_a: str, entity_c: str) -> str:
        """Calibrate a link against a degree-preserving permutation null: stronger than
        random same-degree pairs? Returns a percentile / p-value — the honesty check a
        fresh session can't do itself."""
        return hyp.calibrate_link(entity_a, entity_c)

    @mcp.tool
    def check_novelty(entity_a: str, entity_c: str, via: str = "") -> str:
        """Already PUBLISHED or a genuinely new juxtaposition? PubMed co-mention counts
        distinguish rediscovery from a candidate new hypothesis. Novelty != correctness."""
        return novelty.check_novelty(entity_a, entity_c, via)

    @mcp.tool
    def query_curated_findings(subject: str = "", object: str = "") -> str:
        """The lab's CONSENSUS findings (critic-gated), each with power-weighted confidence,
        evidence count, and KG grounding. What the lab has established / contested / refuted."""
        recs = kg_writer.query(subject or None, object or None)
        if not recs:
            return "No curated findings match (the curated KG may be empty)."
        out = []
        for r in recs[:15]:
            g = kg.check_connection(r["subject"], r["object"])
            res = confidence.score_association(kg_writer.to_association(r),
                                               prior=confidence.grounding_prior(g))
            out.append(f"{r['subject']} —{r['predicate']}→ {r['object']}  "
                       f"[{res.status}, conf {res.confidence:.2f}, "
                       f"{len(r['evidence'])} evidence, KG:{g}]")
        return "\n".join(out)

    @mcp.tool
    def propose_experiment(entity_a: str, entity_c: str, hypothesis: str = "") -> str:
        """Infer the data, study design, statistical tests (Bonferroni+BH, effect sizes,
        power) AND KG-grounded ML methods to test a hypothesized link."""
        return hyp.propose_experiment(entity_a, entity_c, hypothesis)

    @mcp.tool
    def assess_link(entity_a: str, entity_c: str) -> str:
        """Evaluate a candidate link END-TO-END with NO generation: KG grounding + permutation
        calibration + PubMed novelty → a verdict (grounded/published/potential/off-graph), then
        the proposed downstream workflow. The SUBSTRATE half of 'assess an idea' — the client's
        model extracts the entity pair from the free-text idea (a thinking step), this evaluates
        + proposes. Refinement, which uses generation, stays agent-side."""
        import idea
        return idea.assess(entity_a, entity_c)

    @mcp.tool
    def list_active_work() -> str:
        """SHARED WIP ('group semantics'): every tracked hypothesis/experiment/campaign with
        its STATUS — so you can see what's in-flight (mid-test, evaluated, proposed) and NOT
        duplicate it. This is process, not conclusion — provisional, un-gated."""
        import yaml
        lines = ["Shared WIP — tracked work in progress (group semantics):"]
        for f in sorted(glob.glob(str(ROOT / "hypotheses" / "*.y*ml"))):
            d = yaml.safe_load(open(f, encoding="utf-8")) or {}
            hid = d.get("id", Path(f).stem)
            has_exp = (ROOT / "experiments" / hid).exists()
            has_report = (ROOT / "reports" / f"{hid}_evaluation.md").exists()
            gate = ""
            vj = ROOT / "experiments" / hid / "validity.json"
            if vj.exists():
                gates = json.loads(vj.read_text())
                gate = f" · gates {sum(g['passed'] for g in gates)}/{len(gates)}"
            stage = ("evaluated" if has_report else
                     "implemented/running" if has_exp else "spec only")
            lines.append(f"  {hid} [{d.get('status', '?')}] — {stage}{gate}: "
                         f"{str(d.get('title', ''))[:56]}")
        for f in sorted(glob.glob(str(ROOT / "campaigns" / "*.json"))):
            c = json.loads(open(f, encoding="utf-8").read())
            lineage = " → ".join(n["experiment_id"] for n in c.get("nodes", []))
            lines.append(f"  campaign {c['name']}: {lineage}")
        return "\n".join(lines) if len(lines) > 1 else "No tracked work yet."

    @mcp.tool
    def contribute_finding(subject: str, predicate: str, object: str, source: str,
                           source_kind: str = "literature", direction: str = "supports",
                           abstract: str = "", critic_verdict: str = "",
                           critic_reason: str = "") -> str:
        """WRITE-PATH into shared CONSENSUS knowledge (the only gated tier). Normalizes,
        critic-gates (literature → re-reads the abstract; experiment → verified by committed
        provenance), routes CONSERVATIVELY (novel/contradictory → peer review; corroborating
        an already-supported edge → auto-merge), and records with attribution. `source` is a
        PMID or experiment-id; set SUBSTRATE_CONTRIBUTOR for attribution.

        THINKER CRITIC: set `critic_verdict`='accept'|'reject' to supply YOUR judgment (you,
        the client model, are the critic) — the substrate records it WITHOUT running any local
        model. Leave it empty to fall back to the local critic. Pair with `refine_evidence` to
        gather the evidence you judge on."""
        cv = None
        if critic_verdict.strip():
            cv = {"verdict": critic_verdict.strip(),
                  "reason": critic_reason or "verdict supplied by client thinker",
                  "source_supported": critic_verdict.strip().lower() == "accept"}
        return contrib.contribute(subject, predicate, object, source=source,
                                  source_kind=source_kind, direction=direction,
                                  abstract=abstract or None, critic_verdict=cv)

    @mcp.tool
    def refine_evidence(entity_a: str, entity_c: str, max_bridges: int = 4) -> str:
        """Gather the evidence to REFINE a hypothesis with NO generation: each KG bridge's
        mechanism, its A–bridge–C PubMed triple co-mention count, and targeted abstracts. YOU
        (the client model) are the critic — judge each bridge (real lead vs hub/transitivity
        artifact), then record confirmed links via contribute_finding(..., critic_verdict=...).
        The substrate half of the refinement loop; keeps generation on the thinker's side."""
        return hyp.refine_evidence(entity_a, entity_c, max_bridges=max_bridges)

    @mcp.tool
    def review_queue() -> str:
        """Contributions awaiting peer review (novel/contradictory), by contributor."""
        return contrib.review_queue()

    if method_select is not None:
        @mcp.tool
        def recommend_methods(target: str) -> str:
            """KG-grounded ML method selection: given a data modality or disease, traverse
            the fused ML graph for suited architectures (with authorship), losses, metrics,
            and caveats — a graph query, not a lookup."""
            return method_select.recommend_methods(target)

    # --- shared audit surface: the WIP process artifacts ---
    @mcp.resource("substrate://index")
    def index() -> str:
        """What's available: scope, KG backend, tracked experiments/hypotheses/campaigns."""
        exps = sorted(p.name for p in (ROOT / "experiments").glob("H*") if p.is_dir())
        hyps = sorted(Path(p).name for p in glob.glob(str(ROOT / "hypotheses" / "*.y*ml")))
        camps = sorted(Path(p).stem for p in glob.glob(str(ROOT / "campaigns" / "*.json")))
        return json.dumps({"scope": SCOPE, "kg_backend": os.environ.get("KG_BACKEND", "demo"),
                           "experiments": exps, "hypotheses": hyps, "campaigns": camps},
                          indent=2)

    @mcp.resource("provenance://{exp_id}")
    def provenance(exp_id: str) -> str:
        """How an experiment was formed AND tested (deterministic provenance card)."""
        return _read(ROOT / "experiments" / exp_id / "provenance.md", f"provenance for {exp_id}")

    @mcp.resource("report://{exp_id}")
    def report(exp_id: str) -> str:
        """The evaluator's interpretation + verdict for an experiment."""
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


# =========================================================================== #
# PERSONAL tier: your own history + in-progress distillations (local, private) #
# =========================================================================== #
if _PERSONAL:

    @mcp.tool
    def recall_prior_work(query: str, max_results: int = 3) -> str:
        """YOUR episodic memory: has this been explored before in your runs, and what did
        you conclude (incl. negatives)? Local + private."""
        return memory.recall_past_runs(query, max_results)

    @mcp.tool
    def search_notes(query: str, k: int = 5) -> str:
        """Search YOUR personal semantic memory — in-progress distillations, not lab
        consensus. Local + private; reaches shared knowledge only via contribute()."""
        try:
            import semantic_memory
            return semantic_memory.search_semantic(query, k)
        except Exception as err:
            return f"[personal semantic memory unavailable: {err}]"


if __name__ == "__main__":
    mcp.run()   # stdio transport (default)
