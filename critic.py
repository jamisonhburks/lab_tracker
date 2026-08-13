"""critic — adversarial verifier for curated associations (the critic agent).

Judges each extracted association on four axes:
  - well_formed      : are subject/object real biomedical entities (not junk ids,
                       accessions, or vague phrases like 'Overall IBD')?
  - source_supported : does the CITED abstract actually state the relationship?
                       (the hallucination check — re-reads the source)
  - type_valid       : is the predicate compatible with the entity types?
  - plausible        : is the relationship biologically plausible?

Returns a verdict: accept | reject | uncertain, with a reason.

CRUCIAL (per ADR-0008): novelty is NOT a reason to reject. Absence from the KG /
prior knowledge is a signal, never a veto — a novel but plausible, source-supported
link must survive. The critic catches hallucinations and junk, not new ideas.
"""

import json
import urllib.parse
import urllib.request

import ollama

import kg_memory as kg

MODEL = "qwen3:14b"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "well_formed": {"type": "boolean"},
        "source_supported": {"type": "boolean"},
        "type_valid": {"type": "boolean"},
        "plausible": {"type": "boolean"},
        "verdict": {"type": "string"},        # accept | reject | uncertain
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason", "well_formed", "source_supported"],
}


def _fetch_abstract(pmid: str) -> str:
    url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "text"})
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read().decode("utf-8", "replace")[:6000]
    except Exception:
        return ""


def criticize(record: dict, abstract: str | None = None) -> dict:
    """Adversarially verify one association record. `abstract` overrides the fetch
    (used by the eval harness for deterministic, offline tests)."""
    s, p, o = record["subject"], record["predicate"], record["object"]

    if abstract is None:
        pmids = [e["source"].split(":", 1)[1] for e in record.get("evidence", [])
                 if str(e.get("source", "")).startswith("PMID:")]
        abstract = _fetch_abstract(pmids[0]) if pmids else ""

    grounding = kg.check_connection(s, o)
    prompt = (
        "You are an ADVERSARIAL critic of extracted biomedical associations. Try to "
        "find reasons the claim below is WRONG.\n\n"
        f"CLAIM: {s} —{p}→ {o}\n\n"
        "Judge each:\n"
        "- well_formed: are subject and object REAL biomedical entities, not junk "
        "ids/accessions (e.g. 'CID11879209') or vague phrases (e.g. 'Overall IBD')?\n"
        "- source_supported: does the abstract below explicitly state this "
        "relationship? If there is no abstract, set false.\n"
        "- type_valid: is the predicate compatible with the entity types (e.g. a "
        "symptom does not 'treat' a gene)?\n"
        "- plausible: is the relationship biologically plausible?\n\n"
        "verdict: 'reject' if malformed OR unsupported OR type-invalid; 'accept' if "
        "well_formed AND source_supported AND plausible; else 'uncertain'.\n"
        "DO NOT reject a claim merely for being novel or absent from prior knowledge "
        "— a plausible, source-supported new link must be accepted.\n\n"
        f"KG grounding (a hint, NOT decisive): {grounding}\n\n"
        f"ABSTRACT:\n{abstract or '(no source abstract available)'}"
    )
    try:
        resp = ollama.chat(model=MODEL, format=VERDICT_SCHEMA, think=False,
                           messages=[{"role": "user", "content": prompt}])
        verdict = json.loads(resp["message"]["content"])
    except Exception as err:
        return {"verdict": "uncertain", "reason": f"critic error: {err}",
                "grounding": grounding}
    verdict["grounding"] = grounding
    return verdict
