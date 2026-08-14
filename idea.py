"""idea — turn a general idea (or a prior finding) into an evaluated, workflow-ready hypothesis.

The lab's follow-up move: given a rough idea OR a prior experiment, run the SAME evaluation the
substrate offers (grounded / published / potential / off-graph), then propose the downstream
workflow — and only THEN recommend the expensive refinement pass, opt-in.

This is orchestration, not new modeling: it chains tools that already exist.
  1. INTAKE   — free-text idea, or a prior H{NNN} whose title+question+finding seed the idea.
  2. EXTRACT  — the local (frozen) model pulls the testable entity pair(s) from the text.
                Extraction, not learning — consistent with the no-RL / frozen-model stance.
  3. EVALUATE — grounding (kg.check_connection) + calibration (hypothesis_tools) + novelty
                (novelty.classify) → a verdict with guidance. FAST (no curate/critic).
  4. PROPOSE  — hypothesis_tools.propose_experiment → data / design / tests / KG-grounded methods.
  5. REFINE   — recommended, NOT auto-run: the costly novelty-triaged curate+critic loop
                (agent.refine_hypothesis) runs only when refine=True.

`assess(a, c, ...)` is the LLM-free core (testable without the model); `assess_idea(text, ...)`
adds intake + extraction on top.
"""
import re
from pathlib import Path

import kg_memory as kg
import novelty

ROOT = Path(__file__).parent

IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "pairs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string"},
                    "entity_c": {"type": "string"},
                    "relation": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["entity_a", "entity_c"],
            },
        }
    },
    "required": ["pairs"],
}


def _verdict(grounding: str, novelty_status: str) -> tuple:
    """Map (grounding, novelty) -> (label, guidance). This is the 'valid/published/potential'
    call the user described, made explicit."""
    published = novelty_status in ("bridge_published", "established")
    novel = novelty_status in ("novel_bridge", "novel_juxtaposition", "emerging",
                               "emerging_bridge")
    if grounding == "off_graph":
        return ("ungrounded", "Neither entity (or their link) is in the trusted KG. Treat as "
                "speculation — a first study must ESTABLISH the link before mechanism tests apply.")
    if grounding == "novel_unverified":
        return ("novel / unverified", "Entities are known but no trusted path connects them — a "
                "CANDIDATE new link. Calibrate + verify the mechanism before committing.")
    if grounding in ("grounded", "weakly_grounded") and published:
        return ("largely known", "The link is grounded AND well-published — this is replication/"
                "validation, not discovery. Pivot to an unexamined facet, or frame honestly as "
                "confirmation.")
    if grounding == "grounded" and novel:
        return ("promising & testable", "Grounded mechanism that is NOT yet well-published — the "
                "sweet spot. Proceed to the workflow below; consider the refinement pass.")
    if grounding == "weakly_grounded":
        return ("potential", "Only long / low-trust KG paths support this — tenuous. Strengthen "
                "grounding (more evidence) before an expensive experiment.")
    return ("grounded", "Grounded in the KG; novelty inconclusive (PubMed may be unreachable). "
            "Proceed, and check novelty before claiming discovery.")


def assess(entity_a: str, entity_c: str, hypothesis: str = "", refine: bool = False) -> str:
    """LLM-free core: EVALUATE (ground + calibrate + novelty) → verdict → PROPOSE workflow →
    recommend/opt-in the costly REFINE pass. Order matches the lab flow: fast first, expensive
    only on request."""
    import hypothesis_tools as hyp

    grounding = kg.check_connection(entity_a, entity_c)
    nov = novelty.classify(entity_a, entity_c)
    label, guidance = _verdict(grounding, nov.get("status", "unknown"))

    out = [f"### {entity_a}  ↔  {entity_c}",
           f"VERDICT: **{label}** — {guidance}", "",
           "— Evaluation (fast) —",
           f"  KG grounding: {grounding}",
           f"  novelty: {nov.get('status', 'unknown')} "
           f"(PubMed pair co-mentions: {nov.get('n_pair', '?')})",
           "  calibration:"]
    out.append("    " + hyp.calibrate_link(entity_a, entity_c).replace("\n", "\n    "))

    out.append("\n— Downstream workflow (fast) —")
    out.append(hyp.propose_experiment(entity_a, entity_c, hypothesis))

    out.append("\n— Refinement —")
    if refine:
        import agent
        out.append("(running the costly novelty-triaged curate+critic pass)")
        out.append(agent.refine_hypothesis(entity_a, entity_c))
    elif grounding in ("off_graph",):
        out.append("Refinement skipped: no KG bridge to triage (establish a link first).")
    else:
        out.append("RECOMMENDED next: the refinement pass triages each KG bridge by novelty and "
                   "verifies the un-published ones with a targeted literature + critic check "
                   "(writes confirmed links to the curated KG). It is EXPENSIVE (PubMed fetches + "
                   "LLM). Opt in with  assess_idea(..., refine=True)  or  refine_hypothesis().")
    return "\n".join(out)


def _find_prior(ref: str) -> tuple:
    """If `ref` names a prior hypothesis/experiment (e.g. 'H001'), return (seed_text, hyp_id);
    else (None, None). Seeds the idea from the prior title + question + evaluated finding."""
    m = re.match(r"\s*(H\d{1,4})", ref.strip(), re.I)
    if not m:
        return None, None
    hid = m.group(1).upper()
    hits = list((ROOT / "hypotheses").glob(f"{hid}_*.y*ml")) + list((ROOT / "hypotheses").glob(f"{hid}.y*ml"))
    if not hits:
        return None, None
    try:
        import yaml
        d = yaml.safe_load(hits[0].read_text(encoding="utf-8")) or {}
    except Exception:
        return None, None
    parts = [str(d.get("title", "")), str(d.get("question", ""))]
    report = ROOT / "reports" / f"{hid}_evaluation.md"
    if report.exists():
        parts.append("Prior finding: " + report.read_text(encoding="utf-8")[:800])
    return " ".join(p for p in parts if p).strip(), hid


def _extract_pairs(text: str) -> list:
    """Local model pulls the testable entity pair(s) from free text (extraction, not learning)."""
    import llm
    import schemas
    prompt = (
        "From the research idea below, extract the TESTABLE entity pair(s): the two entities "
        "whose relationship the idea proposes to study. Prefer specific, resolvable entities "
        "(genes, diseases, drugs, phenotypes, data modalities). If several distinct links are "
        "implied, return each as its own pair, most central first.\n\n"
        f"IDEA:\n{text}\n\n"
        "Return JSON {'pairs': [{'entity_a', 'entity_c', 'relation', 'rationale'}]}."
    )
    res = llm.parse([{"role": "user", "content": prompt}], IDEA_SCHEMA, schemas.IdeaExtraction)
    return res.pairs


def assess_idea(idea: str, refine: bool = False, max_pairs: int = 2) -> str:
    """Intake a free-text idea OR a prior H{NNN}, extract the entity pair(s), and run the full
    evaluate → propose (→ opt-in refine) chain on each. The single entry point for the lab's
    'follow-up from a general idea / prior work' move."""
    seed_text, prior = _find_prior(idea)
    source = f"follow-up of {prior}" if prior else "free-text idea"
    text = seed_text or idea

    try:
        pairs = _extract_pairs(text)
    except Exception as err:
        return (f"Could not extract an entity pair from the {source} (local model unavailable? "
                f"{err}).\nYou can call  assess(entity_a, entity_c)  directly with the two entities.")
    if not pairs:
        return f"No testable entity pair could be extracted from the {source}."

    head = [f"# Idea assessment — {source}",
            f"> {text[:200]}" + ("…" if len(text) > 200 else ""),
            f"\nExtracted {len(pairs)} candidate pair(s); assessing the top {min(len(pairs), max_pairs)}.\n"]
    blocks = [assess(p.entity_a, p.entity_c, hypothesis=text, refine=refine)
              for p in pairs[:max_pairs]]
    tail = ["\n---",
            "Provenance: KG grounding + permutation calibration + PubMed novelty are the "
            "substrate's checks (not the model's intuition). " +
            ("Refinement ran." if refine else "Refinement was recommended, not run (opt-in).")]
    return "\n".join(head + blocks + tail)


if __name__ == "__main__":
    import sys
    arg = " ".join(sys.argv[1:]) or "does IL6 drive Alzheimer's disease progression?"
    print(assess_idea(arg))
