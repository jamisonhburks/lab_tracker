"""A toy research agent running fully locally on a Qwen3-14B model via Ollama.

The agent loop is model-agnostic: call the model -> if it asked for a tool, run
the tool and feed the result back -> repeat until it stops asking for tools.
The model is reached through the llm.py adapter, so Ollama <-> Claude is a config
flag (LLM_BACKEND) — nothing else in the system knows which provider is used.

Tools (the "grounding" step, per the KG-CoI pattern):
  - search_pubmed    : PubMed abstracts via NCBI E-utilities (no API key).
  - read_file        : read a local file (a hypothesis YAML, a lit note).
  - recall_past_runs : EPISODIC MEMORY — consult what past runs concluded.

After each run, findings are consolidated into claim->sources pairs and written
to episodic memory (memory.py), with sources filtered to what was actually seen.

Prereqs:  ollama pull qwen3:14b  &&  pip install -r requirements.txt
Run:      python agent.py "your question"
"""

import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import llm

import memory
import semantic_memory
import kg_memory as kg
import hypothesis_tools as hyp
import kg_writer
import confidence
import critic
import novelty
import specialist
import tool_ledger
import schemas
import method_select

MAX_STEPS = 10      # safety cap so a misbehaving loop can't run forever
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


# --------------------------------------------------------------------------- #
# Tool implementations — plain Python. Nothing agent-specific here.            #
# --------------------------------------------------------------------------- #

def search_pubmed(query: str, max_results: int = 5) -> str:
    """Search PubMed and return plain-text abstracts of the top hits."""
    search_url = f"{EUTILS}/esearch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"}
    )
    with urllib.request.urlopen(search_url, timeout=30) as resp:
        ids = json.load(resp)["esearchresult"]["idlist"]
    if not ids:
        return "No PubMed results."

    fetch_url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": ",".join(ids), "rettype": "abstract", "retmode": "text"}
    )
    with urllib.request.urlopen(fetch_url, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")[:12000]


def read_file(path: str) -> str:
    """Read a local text file. Read-only on purpose — a toy shouldn't write."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()[:20000]
    except OSError as err:
        return f"Error reading {path}: {err}"


# Per-paper extraction schema. PMID is NOT extracted (it's attached deterministically
# from the paper we fed), and study stats feed the negative-evidence confidence.
STUDY_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "associations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "direction": {"type": "string"},      # supports | refutes
                    "sample_size": {"type": "integer"},
                    "effect_size": {"type": "number"},
                    "p_value": {"type": "number"},
                    "risk_of_bias": {"type": "string"},   # low | some | high
                },
                "required": ["subject", "predicate", "object", "direction"],
            },
        },
    },
    "required": ["associations"],
}


def _fetch_articles(query: str, n: int) -> list:
    """Return [{pmid, title, abstract}] — per-paper, so PMID attribution is exact."""
    search_url = f"{EUTILS}/esearch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "term": query, "retmax": n, "retmode": "json"})
    with urllib.request.urlopen(search_url, timeout=30) as resp:
        ids = json.load(resp)["esearchresult"]["idlist"]
    if not ids:
        return []
    fetch_url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"})
    with urllib.request.urlopen(fetch_url, timeout=30) as resp:
        root = ET.fromstring(resp.read())

    articles = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//PMID")
        title = art.findtext(".//ArticleTitle") or ""
        abstract = " ".join(t.text or "" for t in art.findall(".//AbstractText")).strip()
        if pmid and abstract:
            articles.append({"pmid": pmid, "title": title, "abstract": abstract})
    return articles


def curate_literature(query: str, max_papers: int = 4) -> str:
    """SYNTHESIZER → CURATOR: read papers ONE AT A TIME, extract structured
    associations with study stats, and write them to the agent's KG.

    Per-paper extraction means PMID provenance is exact (we know which paper we
    fed), and captured sample_size / effect_size / risk_of_bias feed the
    negative-evidence-aware confidence scorer with real signal.
    """
    articles = _fetch_articles(query, max_papers)
    if not articles:
        return "No papers found to curate."

    n_assoc, n_stats, n_norm = 0, 0, 0
    for paper in articles:
        prompt = (
            "From this single paper's abstract, extract the biomedical associations "
            "it reports as JSON. For each: subject, predicate (e.g. associates / "
            "treats / upregulates / downregulates / predisposes), object, direction "
            "('supports' or 'refutes' the association), and — ONLY when the abstract "
            "states them — sample_size (study N), effect_size, p_value, and "
            "risk_of_bias ('low' for a large/rigorous study e.g. a big RCT, 'some', "
            "or 'high' for a small/pilot/underpowered study). Extract only what the "
            f"abstract explicitly reports.\n\nAbstract:\n{paper['abstract']}"
        )
        try:
            result = llm.parse([{"role": "user", "content": prompt}],
                               STUDY_EXTRACT_SCHEMA, schemas.StudyExtract)
            assocs = [a.model_dump() for a in result.associations]
        except Exception:
            continue
        for a in assocs:
            subj, pred, obj = (a.get("subject", "").strip(),
                               a.get("predicate", "").strip(), a.get("object", "").strip())
            if not (subj and pred and obj):
                continue
            if a.get("sample_size") or a.get("effect_size") or a.get("risk_of_bias"):
                n_stats += 1
            # normalize entities to canonical KG nodes (dedups variants); keep the
            # raw string if unresolvable — novel entities aren't dropped.
            s_norm, o_norm = kg.normalize_entity(subj), kg.normalize_entity(obj)
            n_norm += bool(s_norm) + bool(o_norm)
            kg_writer.add_association(
                s_norm["name"] if s_norm else subj, pred,
                o_norm["name"] if o_norm else obj,
                source=f"PMID:{paper['pmid']}",
                direction=a.get("direction", "supports"),
                sample_size=a.get("sample_size"), effect_size=a.get("effect_size"),
                p_value=a.get("p_value"), risk_of_bias=a.get("risk_of_bias"),
                subject_id=s_norm["id"] if s_norm else None,
                object_id=o_norm["id"] if o_norm else None)
            n_assoc += 1
    return (f"Curated {n_assoc} association(s) from {len(articles)} paper(s) on "
            f"{query!r} ({n_stats} with study stats, {n_norm} entities normalized "
            f"to KG nodes).")


def criticize_curated_kg(subject: str = "", object: str = "", max_items: int = 10) -> str:
    """Adversarially verify curated associations and persist a verdict on each.

    Catches malformed/unsupported/type-invalid extractions; a novel-but-plausible,
    source-supported link is NOT rejected (KG absence is a hint, not a veto)."""
    recs = kg_writer._load()
    matched = [r for r in recs
               if (not subject or subject.lower() in r["subject"].lower())
               and (not object or object.lower() in r["object"].lower())][:max_items]
    if not matched:
        return "No curated associations to criticize."
    counts, rejected = {"accept": 0, "reject": 0, "uncertain": 0}, []
    for r in matched:
        v = critic.criticize(r)
        r["critic"] = v
        counts[v.get("verdict", "uncertain")] = counts.get(v.get("verdict", "uncertain"), 0) + 1
        if v.get("verdict") == "reject":
            rejected.append((r, v))
    kg_writer._save(recs)   # persist verdicts for audit
    lines = [f"Criticized {len(matched)}: {counts['accept']} accept, "
             f"{counts['reject']} reject, {counts['uncertain']} uncertain."]
    for r, v in rejected[:8]:
        lines.append(f"  REJECT {r['subject']} —{r['predicate']}→ {r['object']}: "
                     f"{str(v.get('reason'))[:80]}")
    return "\n".join(lines)


def query_curated_kg(subject: str = "", object: str = "") -> str:
    """Read the agent's OWN curated KG, each association scored by confidence with
    the reference-KG grounding folded in (a trustworthy subgraph corroborating the
    claim raises its confidence; novel/off-graph adds nothing, never penalizes)."""
    recs = kg_writer.query(subject or None, object or None)
    if not recs:
        return "No curated associations match (the agent's KG may be empty)."
    lines = []
    for r in recs[:15]:
        grounding = kg.check_connection(r["subject"], r["object"])
        result = confidence.score_association(
            kg_writer.to_association(r), prior=confidence.grounding_prior(grounding))
        lines.append(f"{r['subject']} —{r['predicate']}→ {r['object']}  "
                     f"[{result.status}, conf {result.confidence:.2f}, "
                     f"{len(r['evidence'])} evidence, KG:{grounding}]")
    return "\n".join(lines)


# Schema for the HYBRID generation step: an LLM-synthesized mechanistic hypothesis,
# constrained to the KG subgraph it was given (so the graph regularizes invention).
HYPOTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "hypothesis": {"type": "string"},
        "mechanisms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "intermediate": {"type": "string"},
                    "rationale": {"type": "string"},
                    "centrality": {"type": "string"},   # high | moderate | low
                },
                "required": ["intermediate", "rationale", "centrality"],
            },
        },
        "caveats": {"type": "string"},
    },
    "required": ["hypothesis", "mechanisms"],
}


def generate_hypothesis(entity_a: str, entity_c: str, max_len: int = 3) -> str:
    """HYBRID generation: the KG retrieves the subgraph connecting A and C, then the
    MODEL synthesizes a mechanistic hypothesis CONSTRAINED to those paths.

    This is the missing third direction of the hybrid: not KG-only enumeration
    (find_paths) and not LLM-only free generation, but LLM reasoning REGULARIZED by
    the graph — it may only build on intermediates that actually appear in the KG
    paths, which is what suppresses hallucinated mechanisms. The synthesis is then
    annotated with hard numbers (grounding + novelty) so the free-text claim is
    checked, not trusted.
    """
    a, c, paths, truncated = kg.enumerate_paths(entity_a, entity_c, max_len=max_len)
    if a is None or c is None:
        missing = entity_a if a is None else entity_c
        return f"'{missing}' not found in the knowledge graph."
    a_name = kg._meta().get(a, (entity_a, ""))[0]
    c_name = kg._meta().get(c, (entity_c, ""))[0]

    if not paths:
        subgraph = f"(no connecting path in the KG within {max_len} hops)"
        constraint = (
            "There is NO KG-supported path between these entities. Any hypothesis is "
            "UNGROUNDED speculation — say so explicitly and stay cautious; do not "
            "present invented mechanisms as if the graph supported them.")
    else:
        lines, mids = [], {}
        for i, p in enumerate(paths[:10], 1):
            chain = kg._label(p[0][0])
            for _, pred, arrow, src, to_id in p:
                chain += f"  —{pred}{'→' if arrow == '->' else '←'}  {kg._label(to_id)}"
            for mid in ([p[0][0]] + [e[4] for e in p])[1:-1]:   # internal nodes only
                mids.setdefault(mid, kg._meta().get(mid, (mid, ""))[0])
            lines.append(f"  {i}. {chain}")
        subgraph = "\n".join(lines)
        constraint = (
            "Ground EVERY mechanistic claim in one of the specific paths above. Do "
            "NOT introduce genes, drugs, or mechanisms that are not nodes in these "
            "paths — if the graph does not contain it, do not assert it. This "
            "constraint is the point: the KG regularizes the hypothesis against "
            "unsupported invention.")

    prompt = (
        f"You are proposing a mechanistic hypothesis linking '{a_name}' and "
        f"'{c_name}', grounded in a biomedical knowledge graph.\n\n"
        f"KG paths connecting them:\n{subgraph}\n\n{constraint}\n\n"
        "Return JSON: 'hypothesis' (2-4 sentences: the proposed mechanism linking the "
        "two, synthesized from the paths above), 'mechanisms' (one entry per key "
        "intermediate you actually used: intermediate, rationale grounded in its path, "
        "centrality 'high'|'moderate'|'low'), and 'caveats' (what the KG does NOT "
        "establish — directionality, causality, confounders)."
    )
    try:
        h = llm.parse([{"role": "user", "content": prompt}],
                      HYPOTHESIS_SCHEMA, schemas.Hypothesis).model_dump()
    except Exception as err:
        return f"Hypothesis generation failed: {err}"

    out = [f"Hypothesis: {a_name} <-> {c_name}", f"  {h.get('hypothesis', '').strip()}"]
    mechs = h.get("mechanisms", [])
    if mechs:
        out.append("\nMechanisms (KG-grounded):")
        for m in mechs[:8]:
            out.append(f"  - [{m.get('centrality', '?')}] {m.get('intermediate', '?')}: "
                       f"{str(m.get('rationale', '')).strip()[:200]}")
    if h.get("caveats"):
        out.append(f"\nCaveats: {str(h['caveats']).strip()}")

    # Hard-number regularization: is the link corroborated, and is it actually novel?
    top = next((m.get("intermediate") for m in mechs
                if str(m.get("centrality", "")).lower() == "high"),
               mechs[0].get("intermediate") if mechs else None)
    grounding = kg.check_connection(entity_a, entity_c, max_len=max_len)
    out.append(f"\nKG grounding: {grounding}   |  supporting paths: "
               f"{len(paths)}{'+' if truncated else ''}")
    if top:
        out.append("\n" + novelty.check_novelty(a_name, c_name, via=top))
    out.append("\n(Hybrid: KG retrieved the subgraph; the model synthesized the "
               "mechanism CONSTRAINED to it; grounding + novelty regularize the claim.)")
    return "\n".join(out)


def refine_hypothesis(entity_a: str, entity_c: str, max_bridges: int = 4,
                      max_papers: int = 2) -> str:
    """THE LOOP: for each bridge the KG surfaces between A and C, triage whether the
    link is 'already known' — cheaply by novelty, then (for the un-known ones)
    expensively by a targeted literature search + critic pass.

    Cascade: novelty (a PubMed count) decides WHICH bridges deserve the costly
    curate+critic verification; the critic decides whether an unpublished bridge is a
    real new lead or a spurious graph artifact. Verified links are written to the
    curated KG, so next round they count as known — the loop closes.

    EXPENSIVE: up to max_bridges * max_papers PubMed fetches + LLM extractions, plus a
    critic call per curated record. Keep the caps small.
    """
    a, c, paths, _ = kg.enumerate_paths(entity_a, entity_c)
    if a is None or c is None:
        missing = entity_a if a is None else entity_c
        return f"'{missing}' not found in the knowledge graph."
    if not paths:
        return f"No KG path connects {kg._label(a)} and {kg._label(c)} — nothing to refine."
    a_name = kg._meta().get(a, (entity_a, ""))[0]
    c_name = kg._meta().get(c, (entity_c, ""))[0]

    # Bridges: distinct internal nodes, shortest paths first.
    bridges = {}
    for p in paths:
        for mid in ([p[0][0]] + [e[4] for e in p])[1:-1]:
            bridges.setdefault(mid, kg._meta().get(mid, (mid, ""))[0])
    bridges = dict(list(bridges.items())[:max_bridges])

    rows = []
    for bname in bridges.values():
        nov = novelty.classify(a_name, c_name, via=bname)
        if nov["status"] == "bridge_published":       # cheap filter says: already known
            rows.append((bname, nov["status"], nov["n_bridge"], 0, 0, "known — rediscovery"))
            continue
        # Un-known bridge: run the expensive verification (targeted lit search + critic).
        before = {kg_writer._rec_key(r) for r in kg_writer._load()}
        curate_literature(f"{a_name} {bname} {c_name}", max_papers=max_papers)
        new = [r for r in kg_writer._load() if kg_writer._rec_key(r) not in before]
        rel = [r for r in new if bname.lower() in r["subject"].lower()
               or bname.lower() in r["object"].lower()]
        accepted = sum(1 for r in rel
                       if (v := critic.criticize(r)).get("verdict") == "accept"
                       and v.get("source_supported"))
        label = ("supported — real link (verify)" if accepted > 0 else
                 "unsupported — likely spurious" if rel else
                 "no evidence found — speculative")
        rows.append((bname, nov["status"], nov["n_bridge"], len(rel), accepted, label))

    # Order: known first, then supported, then spurious/speculative.
    order = {"known — rediscovery": 0, "supported — real link (verify)": 1,
             "unsupported — likely spurious": 2, "no evidence found — speculative": 3}
    rows.sort(key=lambda r: order.get(r[5], 9))

    out = [f"Refinement loop: {a_name} <-> {c_name}  ({len(bridges)} bridge(s) triaged)",
           f"{'BRIDGE':<16} {'NOVELTY':<18} {'TRIPLE':>6} {'CUR':>4} {'OK':>3}  VERDICT"]
    for bname, status, ntriple, ncur, nok, label in rows:
        out.append(f"{str(bname)[:16]:<16} {status:<18} {str(ntriple):>6} "
                   f"{ncur:>4} {nok:>3}  {label}")
    out += ["", "known=already published; supported=lit+critic confirmed real "
            "evidence; spurious=novelty-flagged but unverifiable. Verified links were "
            "written to the curated KG (they count as known next round)."]
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Tool declarations — what the MODEL sees.                                     #
# --------------------------------------------------------------------------- #

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_pubmed",
            "description": (
                "Search PubMed for biomedical abstracts. Call this whenever the "
                "question involves prior work, evidence, mechanisms, or novelty. "
                "Ground claims in the results — do not guess."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "PubMed search terms."},
                    "max_results": {"type": "integer", "description": "1-10, default 5."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a local text file (e.g. a hypothesis YAML under hypotheses/ "
                "or a note under literature/). Call this to ground answers in the "
                "user's own project files instead of assuming their contents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute path."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_semantic",
            "description": (
                "Search SEMANTIC MEMORY — durable facts distilled from past runs, "
                "recalled by meaning. Call this to check what is already known "
                "before searching PubMed, since a prior run may have established it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What fact to look up."},
                    "k": {"type": "integer", "description": "How many facts, default 5."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_past_runs",
            "description": (
                "Consult EPISODIC MEMORY of previous runs. Call this at the START "
                "of a task to check whether this question has been investigated "
                "before and what was concluded, so you can build on it rather than "
                "start over."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look up in past runs."},
                    "max_results": {"type": "integer", "description": "1-5, default 3."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_graph",
            "description": (
                "Query the biomedical KNOWLEDGE GRAPH for an entity's typed "
                "relationships (disease-gene, drug-disease, phenotype), each with "
                "its source. Use for mechanistic 'what is X connected to' questions "
                "that go beyond free-text search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity name, e.g. 'atrial fibrillation'."},
                },
                "required": ["entity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_paths",
            "description": (
                "Find connecting paths A->B->C between two biomedical entities in "
                "the knowledge graph — the core hypothesis-generation move for "
                "surfacing indirect, mechanistic links (e.g. a shared gene)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string"},
                    "entity_c": {"type": "string"},
                    "max_len": {"type": "integer", "description": "Max hops, default 3."},
                },
                "required": ["entity_a", "entity_c"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_hypothesis",
            "description": (
                "HYBRID hypothesis generation: retrieve the KG subgraph connecting "
                "two entities, then SYNTHESIZE a mechanistic hypothesis constrained "
                "to those paths (the model may only build on intermediates that "
                "appear in the graph — this regularizes hallucination). Use this "
                "instead of find_paths when you want a reasoned mechanism, not just "
                "a path list. Output is annotated with KG grounding + literature "
                "novelty."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string"},
                    "entity_c": {"type": "string"},
                },
                "required": ["entity_a", "entity_c"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refine_hypothesis",
            "description": (
                "Run THE REFINEMENT LOOP over the bridges linking two entities: "
                "triage each shared intermediate as already-known (novelty), then "
                "for the un-known ones run a targeted literature search + critic "
                "pass to decide real-new-lead vs spurious. Returns a triage table "
                "and writes verified links to the curated KG. Expensive — use when "
                "you want to separate rediscovery from genuine candidates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string"},
                    "entity_c": {"type": "string"},
                },
                "required": ["entity_a", "entity_c"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_novelty",
            "description": (
                "Is a hypothesized link already PUBLISHED, or a genuinely new "
                "juxtaposition? The KG is built from the literature, so every edge "
                "is known — this asks PubMed whether A, C (and an optional bridge "
                "gene 'via') are already co-mentioned. Distinguishes rediscovery "
                "('established'/'bridge_published') from a candidate new hypothesis "
                "('novel_juxtaposition'). Novelty is NOT correctness — a reason to "
                "verify, not to trust."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string"},
                    "entity_c": {"type": "string"},
                    "via": {"type": "string", "description": "Optional bridge entity (e.g. a shared gene)."},
                },
                "required": ["entity_a", "entity_c"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assess_hypothesis",
            "description": (
                "Score how well the knowledge graph SUPPORTS a hypothesized link "
                "between two entities (a realism metric from path abundance, "
                "directness, and independent sources). Call after proposing a "
                "hypothesis to gauge its plausibility."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string"},
                    "entity_c": {"type": "string"},
                },
                "required": ["entity_a", "entity_c"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_methods",
            "description": (
                "KG-grounded ML METHOD selection: given a data modality (e.g. 'ECG', "
                "'longitudinal event-based EHR') or a disease, traverse the fused ML graph "
                "to return suited architectures (with authorship), their losses, metrics, "
                "and caveats — a graph query, not a lookup table. EHR splits into "
                "event-based (OMOP/MEDS→sequence models) vs aggregated tabular (→XGBoost)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "A data modality or disease name."},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_experiment",
            "description": (
                "Infer what DATA, DATASETS, METHODS, and STATISTICAL TESTS would be "
                "needed to actually test a hypothesized link between two entities. "
                "Grounded in the mechanism types on the KG paths."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string"},
                    "entity_c": {"type": "string"},
                    "hypothesis": {"type": "string", "description": "The hypothesis, optional."},
                },
                "required": ["entity_a", "entity_c"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calibrate_link",
            "description": (
                "CALIBRATE a hypothesized link against a degree-preserving null: is "
                "this pair's connection stronger than random pairs of the same "
                "degree? Returns a percentile / p-value. Use to check whether a high "
                "realism score is real signal or just graph-density/hub inflation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string"},
                    "entity_c": {"type": "string"},
                },
                "required": ["entity_a", "entity_c"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "curate_literature",
            "description": (
                "SYNTHESIZE + CURATE: search PubMed for a topic, extract the stated "
                "biomedical associations, and WRITE them into the agent's own "
                "knowledge graph with provenance. Use to grow durable structured "
                "knowledge from the literature, not just answer once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic to curate."},
                    "max_papers": {"type": "integer", "description": "1-10, default 5."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "criticize_curated_kg",
            "description": (
                "Deploy the CRITIC: adversarially verify curated associations "
                "(well-formed? source-supported? type-valid? plausible?) and record "
                "a verdict on each. Rejects hallucinations/junk but keeps novel "
                "plausible links. Use to clean the curated KG after curation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Filter by subject."},
                    "object": {"type": "string", "description": "Filter by object."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_curated_kg",
            "description": (
                "Read the agent's OWN curated knowledge graph — associations it "
                "extracted from past literature, each with a confidence score. Check "
                "here for structured knowledge the agent already distilled."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Filter by subject entity."},
                    "object": {"type": "string", "description": "Filter by object entity."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_specialist",
            "description": (
                "Delegate a SCIENTIFIC COMPUTATION task to the Claude specialist, "
                "which runs domain Agent Skills (cohort tables, survival-analysis "
                "plans, biomarker/model evaluation, de-identification checks, "
                "experimental design, stats, biopython). Use when a hypothesis needs "
                "real analysis/artifacts beyond KG/literature reasoning. Pass only "
                "de-identified/aggregate inputs — raw patient data stays local."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The computation task, with any de-identified/aggregate inputs or file paths."},
                },
                "required": ["task"],
            },
        },
    },
]

DISPATCH = {
    "search_pubmed": search_pubmed,
    "read_file": read_file,
    "recall_past_runs": memory.recall_past_runs,
    "search_semantic": semantic_memory.search_semantic,
    "query_graph": kg.query_graph,
    "find_paths": kg.find_paths,
    "generate_hypothesis": generate_hypothesis,
    "refine_hypothesis": refine_hypothesis,
    "check_novelty": novelty.check_novelty,
    "assess_hypothesis": hyp.assess_hypothesis,
    "recommend_methods": method_select.recommend_methods,
    "propose_experiment": hyp.propose_experiment,
    "calibrate_link": hyp.calibrate_link,
    "curate_literature": curate_literature,
    "criticize_curated_kg": criticize_curated_kg,
    "query_curated_kg": query_curated_kg,
    "run_specialist": specialist.run_specialist,
}

# Schema for the consolidation step: findings as claim -> sources pairs.
CONSOLIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "subject": {"type": "string"},
                    "object": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim", "subject", "object", "sources"],
            },
        },
    },
    "required": ["findings"],
}


# Pre-flight tool plan: the agent declares which tools it EXPECTS to need, before
# acting — captured in the tool ledger and diffed against what it actually uses.
TOOL_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "intended": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"tool": {"type": "string"}, "why": {"type": "string"}},
                "required": ["tool"],
            },
        },
    },
    "required": ["intended"],
}


def _plan_tools(question: str) -> list:
    """Ask the model which tools it expects to need (intended plan), in anticipated
    order. Best-effort — a failed/empty plan never blocks the run."""
    names = {t["function"]["name"] for t in TOOLS}
    catalog = "\n".join(f"- {t['function']['name']}: {t['function']['description'][:90]}"
                        for t in TOOLS)
    prompt = (
        f"Task: {question}\n\nYour available tools:\n{catalog}\n\n"
        "Before acting, PLAN: list ONLY the few tools you are genuinely confident you "
        "will call for THIS task, in the order you anticipate calling them, each with a "
        "one-line reason. Be selective — a focused plan of 1–5 tools is expected; do NOT "
        "list tools you merely might use."
    )
    try:
        plan = llm.parse([{"role": "user", "content": prompt}], TOOL_PLAN_SCHEMA, schemas.ToolPlan)
        return [{"tool": it.tool, "why": it.why} for it in plan.intended if it.tool in names]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# The agent loop.                                                             #
# --------------------------------------------------------------------------- #

def run_agent(question: str) -> None:
    messages = [{"role": "user", "content": question}]
    tool_log = []
    seen = set()   # provenance actually observed this run (PMID:… / file:…)

    ledger = tool_ledger.ToolLedger(task=question)      # intended-vs-actual tool trace
    ledger.plan(_plan_tools(question))
    if ledger.intended:
        print("[planned tools: " + ", ".join(i["tool"] for i in ledger.intended) + "]")

    for _ in range(MAX_STEPS):
        resp = llm.chat(messages, tools=TOOLS)

        if resp.text:
            print(resp.text)

        if not resp.tool_calls:
            break

        messages.append({"role": "assistant", "content": resp.text,
                         "tool_calls": [{"id": tc.id, "name": tc.name, "args": tc.args}
                                        for tc in resp.tool_calls]})
        for tc in resp.tool_calls:
            name, args = tc.name, tc.args
            print(f"  -> calling {name}({args})")
            output = DISPATCH[name](**args)

            tool_log.append({"name": name, "args": args})
            ledger.record(name, args, layer="orchestrator")   # actual, in order
            # Any tool output can carry provenance — a fresh PubMed hit, or a PMID
            # recalled from memory — so scan them all and let grounding carry forward.
            seen.update(f"PMID:{m}" for m in re.findall(r"PMID:\s*(\d+)", output))
            if name == "read_file":
                seen.add(f"file:{args.get('path', '')}")
            if name in ("query_graph", "find_paths"):   # KG edges cite databases
                for s in re.findall(r"source: ([^)\n]+)", output):
                    seen.add(f"KG:{s.strip()}")
                for grp in re.findall(r"via: (.+)", output):
                    seen.update(f"KG:{s.strip()}" for s in grp.split(","))

            messages.append({"role": "tool", "tool_call_id": tc.id, "name": name,
                             "content": output})
    else:
        print("\n[stopped: hit MAX_STEPS]")

    findings = _consolidate(messages, seen)
    _ground_findings(findings)   # KG-as-verifier: corroborate each claim's link
    entry = memory.record_run(question, tool_log, findings)
    n_src = sum(len(f["sources"]) for f in findings)
    print(f"\n[episodic memory: saved {entry['id']} — "
          f"{len(findings)} claim(s), {n_src} source link(s)]")

    ledger.run_id = entry["id"]           # tie the tool trace to this run
    ledger.save()
    print(ledger.summary())

    # Hybrid grounding summary. Uncorroborated != false — the KG is incomplete, so
    # a claim with no trustworthy path may be genuinely novel and worth verifying.
    tally = {}
    for f in findings:
        tally[f.get("grounding", "n/a")] = tally.get(f.get("grounding", "n/a"), 0) + 1
    if tally.get("grounded") or tally.get("weakly_grounded"):
        print(f"[KG grounding: "
              f"{tally.get('grounded', 0)} grounded (trustworthy path), "
              f"{tally.get('weakly_grounded', 0)} weak, "
              f"{tally.get('novel_unverified', 0)} novel/unverified, "
              f"{tally.get('off_graph', 0)} off-graph — "
              f"novel/unverified are NOT false, they need verification]")

    # Consolidate: distil each finding into durable, embedded semantic memory.
    n_new = sum(bool(semantic_memory.add_fact(f["claim"], f["sources"])) for f in findings)
    print(f"[semantic memory: +{n_new} new fact(s)]")


def _consolidate(messages: list, seen: set) -> list:
    """One schema-constrained call: bind each claim to sources it actually used.

    The model proposes claim->sources; we then drop any source it didn't
    genuinely retrieve this run, so stored provenance is always real.
    """
    prompt = (
        "Summarize your findings as JSON. For each empirical claim you made, list "
        "the exact source ids that support it, drawn ONLY from the tool results "
        "above (PubMed ids as 'PMID:xxxxx', files as 'file:<path>', knowledge-graph "
        "sources as 'KG:<database>'). If a claim has no supporting source, use an "
        "empty list. Also give 'subject' and 'object': the two biomedical entities "
        "the claim relates (short canonical names, e.g. 'Crohn's disease', 'CXCL8'), "
        "or empty strings if the claim is not a relation between two named entities."
    )
    try:
        result = llm.parse(messages + [{"role": "user", "content": prompt}],
                           CONSOLIDATION_SCHEMA, schemas.Consolidation)
        findings = [f.model_dump() for f in result.findings]
    except Exception as err:  # keep the toy robust if consolidation hiccups
        print(f"[consolidation failed: {err}]")
        return []

    for f in findings:
        f["sources"] = [s for s in f.get("sources", []) if s in seen]
    return [f for f in findings if f.get("claim")]


def _ground_findings(findings: list) -> None:
    """KG-as-verifier (hybrid). Tag each relational claim by how well a trustworthy
    KG subgraph corroborates it. 'novel_unverified'/'off_graph' mean the KG can't
    confirm it — NOT that it's false (the graph is incomplete)."""
    for f in findings:
        subj, obj = f.get("subject", "").strip(), f.get("object", "").strip()
        f["grounding"] = kg.check_connection(subj, obj) if subj and obj else "n/a"


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--repl"]
    if args:                                  # single-shot:  python agent.py "question"
        run_agent(" ".join(args))
    else:                                      # persistent REPL: KG + model stay warm
        # The KG (and its indexes) load once and are reused across every question in
        # this session — no ~20s reload per run. Same for the Ollama model.
        print("Warming up the knowledge graph (loaded once, reused across questions)...")
        kg._graph()
        print("Ready. Ask a research question — empty line or 'quit' to exit.")
        while True:
            try:
                question = input("\n> ").strip()
            except EOFError:
                break
            if not question or question.lower() in ("quit", "exit"):
                break
            run_agent(question)
