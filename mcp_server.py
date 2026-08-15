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

Transports (see docs/deployment.md):
  - stdio (default): local, per-user  →  `python mcp_server.py`
  - HTTP (shared lab deployment): one instance on a cluster node serves everyone  →
      `MCP_TRANSPORT=http MCP_HOST=0.0.0.0 MCP_PORT=8443 SUBSTRATE_SCOPE=shared \
       KG_BACKEND=combined python mcp_server.py`   (KG loaded once; per-request attribution
      from the `X-Substrate-Contributor` header; writes serialized via store_lock).

Client (Claude Desktop) — add to claude_desktop_config.json: a `lab-shared` HTTP entry
(`"url": "https://lab-node:8443/mcp"`) + a local `my-personal` stdio entry
(`{"command":"python","args":["/ABS/PATH/mcp_server.py"],"env":{"SUBSTRATE_SCOPE":"personal"}}`).
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
import beliefs
import calibration
import misc_research as misc
import deep_search as deep
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


def _caller() -> str | None:
    """Per-request contributor identity for the SHARED HTTP deployment: the `X-Substrate-
    Contributor` header (set by the lab member's client, or a reverse proxy after auth), so
    writes are attributed to the actual person — not the server's process user. Returns None
    over stdio (single-user), where writes fall back to SUBSTRATE_CONTRIBUTOR/$USER."""
    try:
        from fastmcp.server.dependencies import get_http_headers
        h = get_http_headers() or {}
        return h.get("x-substrate-contributor") or h.get("x-forwarded-user") or None
    except Exception:
        return None


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
            b = beliefs.current(r["subject"], r["predicate"], r["object"])
            trend = f" {beliefs._arrow(b['delta'])}{b['delta']:+.2f}" if b and b.get("delta") \
                is not None else ""      # how belief last moved (the "living" signal)
            out.append(f"{r['subject']} —{r['predicate']}→ {r['object']}  "
                       f"[{res.status}, conf {res.confidence:.2f}{trend}, "
                       f"{len(r['evidence'])} evidence, KG:{g}]")
        return "\n".join(out)

    @mcp.tool
    def belief(subject: str, predicate: str, object: str) -> str:
        """The lab's CURRENT belief in one consensus edge — confidence, status, and how it LAST
        MOVED (the delta + who moved it). Belief is live state that updates as evidence accrues,
        not a static label. Use belief_history for the full trajectory."""
        return beliefs.render_current(subject, predicate, object)

    @mcp.tool
    def belief_history(subject: str, predicate: str, object: str) -> str:
        """The belief TRAJECTORY for an edge — the sequence of evidence that moved the lab's
        confidence over time (0.48→0.55→0.61 …), each step attributed. This is the provenance
        of the confidence itself: *why* the lab believes it as strongly as it does."""
        return beliefs.render_history(subject, predicate, object)

    @mcp.tool
    def contradictions() -> str:
        """The open CONTRADICTION LEDGER: consensus edges where a new claim OPPOSES an
        established belief, kept side-by-side and unresolved. Where the lab's knowledge is
        genuinely in tension — surfaced, not silently overwritten."""
        return beliefs.render_conflicts()

    @mcp.tool
    def resolve_contradiction(conflict_id: str, resolution: str, rationale: str = "") -> str:
        """Adjudicate an open contradiction (see contradictions()). `resolution`: upheld
        (established belief stands) | overturned (the incoming claim wins) | contested (both
        genuinely stand — the edge is disputed). YOU, the thinker, judge; the substrate only
        records the tension and your verdict (append-only, attributed)."""
        return beliefs.resolve_conflict(conflict_id, resolution, by=_caller() or "", rationale=rationale)

    @mcp.tool
    def calibration_audit(lens: str = "all") -> str:
        """Is the lab's confidence CALIBRATED? Scores the confidence numbers the substrate emits
        against realized outcomes it already generates — resolved contradictions (adjudicated) and
        belief reversals (stability) — into a reliability table, ECE, and an honest over/under-
        confidence verdict. `lens`: all | adjudicated | stability. Stays HUMBLE below a data floor
        rather than reporting a misleading number. The substrate auditing its OWN confidence."""
        return calibration.render(lens)

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
    def research_story(campaign: str = "") -> str:
        """An HONEST narrative of a project's arc (a campaign, or all hypotheses) — NOT a highlight
        reel. Each step interweaves what went well with the CAVEATS (validity gates, grounding/
        novelty, power, synthetic-vs-real, the evaluator's own words) and concrete ways to SOLIDIFY
        the finding, ending on the arc's weakest link. Great for morale AND the paper's discussion."""
        import research_story as rs
        return rs.story(campaign)

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
                                  abstract=abstract or None, critic_verdict=cv,
                                  contributor=_caller())

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

    @mcp.tool
    def graduation_candidates(min_sources: int = 3) -> str:
        """Distilled/curated edges backed by >= min_sources INDEPENDENT sources that aren't in the
        consensus pipeline yet — well-corroborated enough to PROPOSE to gated consensus. The bridge
        from the literature-evidence layer (deep-search distillations) to what the lab believes."""
        return contrib.graduation_candidates(min_sources)

    @mcp.tool
    def graduate(subject: str, predicate: str, object: str, critic_verdict: str = "",
                 critic_reason: str = "") -> str:
        """Graduate a well-corroborated distilled edge (see graduation_candidates) from the
        evidence layer into GATED consensus — routes through the critic gate (novel → peer review;
        corroborating → auto-merge). Supply critic_verdict='accept'|'reject' as YOUR judgment."""
        cv = None
        if critic_verdict.strip():
            cv = {"verdict": critic_verdict.strip(), "reason": critic_reason or "thinker verdict",
                  "source_supported": critic_verdict.strip().lower() == "accept"}
        return contrib.graduate(subject, predicate, object, critic_verdict=cv, contributor=_caller())

    @mcp.tool
    def log_misc_finding(claim: str, subject: str = "", object: str = "", method: str = "",
                         effect_size: float | None = None, p_value: float | None = None,
                         sample_size: int | None = None, source: str = "",
                         rigor_verdict: str = "") -> str:
        """Log a MISCELLANEOUS (un-hypothesized) analysis result into the lab's exploratory pool.
        Still RIGOR-gated (claim + method + evidence; underspecified ones are FLAGGED, not
        dropped) and auto-matched against the lab KG / consensus / active hypotheses. Not
        consensus — it lives in the exploratory pool until it matches or is grouped + formalized.
        `rigor_verdict` ('accept'|'flag'|'reject') lets YOU (the thinker) supply the rigor call;
        else a heuristic runs."""
        return misc.log_misc(claim, subject=subject, object=object, method=method,
                             effect_size=effect_size, p_value=p_value, sample_size=sample_size,
                             source=source, rigor_verdict=rigor_verdict.strip() or None,
                             contributor=_caller())

    @mcp.tool
    def match_misc_finding(subject: str, object: str) -> str:
        """Match a candidate finding against the coherent lab knowledge (KG grounding + curated
        consensus + active hypotheses): corroborates / relates-to-Hxxx / grounded-novel / orphan."""
        return json.dumps(misc.match_misc(subject, object), indent=2)

    @mcp.tool
    def group_misc_findings() -> str:
        """Cluster the exploratory pool by shared entity — KG-normalized so SYNONYMS collapse
        (plus an embedding merge for off-graph synonyms). Each cluster of scattered analyses may
        imply a latent hypothesis; formalize one with formalize_misc_group(N)."""
        return misc.group_misc()

    @mcp.tool
    def formalize_misc_group(theme: int = 1) -> str:
        """Turn a GROUP of misc findings (theme N from group_misc_findings) straight into a DRAFT
        hypothesis + method stub — one step from scattered analyses to a formalizable hypothesis.
        Review/complete, then save to hypotheses/H00N_*.yaml (shared WIP)."""
        return misc.formalize_group(theme)

    @mcp.tool
    def list_misc_findings() -> str:
        """The lab's exploratory (un-hypothesized) findings pool, with rigor + match status."""
        return misc.list_misc()

    @mcp.tool
    def deep_search_status(topic: str, subject: str = "", object: str = "") -> str:
        """BEFORE a big online literature search: has this topic/entity-pair ALREADY been deep-
        searched (cache) or is it already covered by curated edges? If so, corroborate against the
        KG and skip the redundant sweep — the whole point is not to repeat expensive searches."""
        return deep.search_status(topic, subject, object)

    @mcp.tool
    def deep_fetch(topic: str, extra_terms: str = "", max_papers: int = 8) -> str:
        """Broad multi-query PubMed fetch (NO LLM) — the topic + any comma-separated query
        variants YOU supply — deduped. Returns a corpus of abstracts for YOU to distill into
        structured associations, which you then submit via record_distillation."""
        variants = [t for t in extra_terms.split(",") if t.strip()]
        return deep.deep_fetch(topic, extra_terms=variants, max_papers=max_papers)

    @mcp.tool
    def stale_topics(older_than_days: int = 180) -> str:
        """Deep-searched topics whose cache has gone STALE (literature moves) — candidates for a
        refresh. A scheduled job (refresh_stale.py, cron) re-distils these; this tool surfaces them."""
        stale = deep.stale_topics(older_than_days)
        if not stale:
            return f"No topics older than {older_than_days}d — the deep-search cache is fresh."
        return f"{len(stale)} stale topic(s) (>{older_than_days}d):\n" + "\n".join(
            f"  {s['age_days']}d  {s['topic']!r}  (last by {s['contributor']} on {s['ts'][:10]})"
            for s in stale[:20])

    @mcp.tool
    def record_distillation(topic: str, associations: list, pmids: list | None = None) -> str:
        """Write YOUR distilled associations (from a deep_fetch corpus) into the PRIMARY KG with
        provenance, and CACHE the topic so the lab doesn't repeat the search. Each association:
        {subject, predicate, object, direction, source: 'PMID:...', effect_size?, p_value?,
        sample_size?}. Malformed / source-less ones are skipped. Literature-evidence layer
        (queryable immediately) — not the gated consensus tier."""
        return deep.record_distillation(topic, associations, pmids=pmids, contributor=_caller())

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

    # --- session journal: keep the personal tier alive DURING a live session --- #
    _JOURNAL = {"j": None}

    def _journal():
        if _JOURNAL["j"] is None:
            import session_journal
            _JOURNAL["j"] = session_journal.SessionJournal(
                session_id=os.environ.get("SESSION_ID"))
        return _JOURNAL["j"]

    @mcp.tool
    def journal_note(text: str) -> str:
        """Append a note to THIS session's personal notes (local, private). Jot ideas,
        candidate hypotheses, methods, partial results as you work."""
        _journal().note(text)
        return "noted."

    @mcp.tool
    def journal_checkpoint() -> str:
        """Checkpoint the session notes: record what CHANGED since last time, with provenance
        (append-only, timestamped, content-hashed). Call periodically (e.g. hourly — drive it
        from your client's scheduler) so a long active session keeps a durable trail."""
        return _journal().checkpoint(force=True) or "no change since last checkpoint."

    @mcp.tool
    def promotion_review() -> str:
        """Once enough has accrued in your personal notes, recommend which components are
        ready to propose UP to SHARED WIP (hypotheses → YAML, experiments → dirs, findings →
        contribute after testing). A recommendation only — nothing is promoted automatically."""
        return _journal().promotion_review()

    @mcp.tool
    def session_check() -> str:
        """Detect whether THIS session is hypothesis-driven or an ad-hoc SERIES of tests with no
        setup. If ad-hoc, it asks whether to attach the Research Workflow retroactively
        (formalize a hypothesis + methods) OR log the work as miscellaneous (rigor-checked +
        matched to the lab KG). Nudges unstructured analysis toward the coherent lab record."""
        j = _journal()
        return f"session mode: {j.session_mode()}" + (j.workflow_suggestion() or
                                                      "\n(no workflow action needed yet)")

    @mcp.tool
    def formalize_retroactively() -> str:
        """Attach the Research Workflow AFTER the fact: draft a hypothesis + method stub from
        this session's ad-hoc analyses (recurring entities → the link; experiment notes → the
        method). A DRAFT to review/complete, then save to hypotheses/H00N_*.yaml (shared WIP)."""
        return _journal().formalize_retroactively()

    @mcp.tool
    def warm_start() -> str:
        """Your WARM START — call it when you open a session: where you left off, what changed in
        the lab since you were last here, what's waiting on you, and one suggested next step.
        A colleague's rundown that composes your journal + the shared WIP/consensus (read-only)."""
        import briefing
        return briefing.briefing(_caller())

    @mcp.tool
    def serendipity() -> str:
        """Surprising, RELEVANT connections you didn't go looking for — your work meeting a
        colleague's, an active hypothesis touching your entities, and LATENT KG bridges between
        two of your own entities. Deduped (each shown once) so it delights, not spams."""
        import serendipity as ser
        nd = ser.nudges(_caller(), max_nudges=4, deep=True, mark=True)
        return "✨ Serendipity:\n" + "\n".join(f"  • {n}" for n in nd) if nd else \
            "No fresh serendipity right now — keep working; the connections will come."


if __name__ == "__main__":
    # Local per-user: stdio (default). Shared lab deployment: MCP_TRANSPORT=http on a cluster
    # node, one instance serving everyone over streamable HTTP. See docs/deployment.md.
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport in ("http", "streamable-http"):
        mcp.run(transport="http",
                host=os.environ.get("MCP_HOST", "127.0.0.1"),
                port=int(os.environ.get("MCP_PORT", "8000")))
    else:
        mcp.run()   # stdio transport (default)
