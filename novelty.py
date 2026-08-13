"""novelty — is a KG-surfaced link already published, or a genuinely new juxtaposition?

The KG is built FROM the literature, so any single edge (A—G, G—C) is, by
construction, already published. What may be NEW is the JUXTAPOSITION: that the
same intermediate G links BOTH A and C. This is the Swanson "undiscovered public
knowledge" move — the pieces are known, but nobody has connected A to C through G.

This module asks PubMed whether A, C, and the bridge G are already CO-mentioned,
and classifies the link:

When a bridge `via` is given, the SPECIFIC gene-mediated relationship is judged on
the A–G–C triple — NOT on the pair. A well-worn comorbidity (A–C) can still hide an
unpublished mechanism (a particular shared gene nobody has connected to both):

  - bridge_published    : the A–G–C triple is well represented (>= BRIDGE_KNOWN_N
                          papers) — this specific mechanism is already known.
  - emerging_bridge     : the triple appears a little — the mechanism is lightly
                          studied, not yet established.
  - novel_bridge        : the pair A–C is studied but the G-mediated link is NOT in
                          the literature — a CANDIDATE mechanism for a known
                          comorbidity (verify before trusting).
  - novel_juxtaposition : neither the pair nor the bridge appears — a fully new link.

With no bridge, the PAIR is judged: established / emerging / novel_juxtaposition.

CRUCIAL (mirrors ADR-0008's closed-world humility, inverted): novelty is NOT
correctness. A never-published bridge can be spurious — an indirect graph path with
no real mechanism (exactly the weak-tier genes the critic flags). The flag is a
REASON TO CHECK, never a claim of truth. It is one step in a LOOP: novelty flags an
unpublished bridge -> a targeted literature search on that specific target -> the
critic pass decides real-new vs spurious -> the verdict refines what counts as
"already known". Pair it with calibrate_link (is the link above chance?) too.

No API key needed (NCBI E-utilities). Counts only — we fetch retmax=0 and read the
reported hit count, so this is cheap.
"""

import json
import urllib.parse
import urllib.request

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# A pair with at least this many joint PubMed papers is a well-worn, "established"
# co-study — the comorbidity itself is not a new idea.
ESTABLISHED_N = 50
# A specific A–bridge–C triple this well represented is an already-known mechanism;
# below it (but > 0) the mechanism is only lightly studied.
BRIDGE_KNOWN_N = 10


def _pubmed_count(term: str) -> int:
    """Number of PubMed records matching `term` (retmax=0 -> just the count)."""
    url = f"{EUTILS}/esearch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "term": term, "retmax": 0, "retmode": "json"})
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return int(json.load(r)["esearchresult"]["count"])
    except Exception:
        return -1        # signal "could not query" rather than a false zero


def _q(s: str) -> str:
    """Quote a multi-word entity so PubMed treats it as a phrase."""
    s = s.strip().strip('"')
    return f'"{s}"' if " " in s else s


def check_novelty(entity_a: str, entity_c: str, via: str = "") -> str:
    """Classify how NOVEL a hypothesized A–C link (optionally through bridge `via`)
    is against the published literature. Distinguishes rediscovery from a genuinely
    new juxtaposition — the thing the KG cannot tell you on its own, because every
    KG edge is already published.

    `via` is the intermediate (e.g. a shared gene) the KG used to connect A and C.
    """
    pair_term = f"{_q(entity_a)} AND {_q(entity_c)}"
    n_pair = _pubmed_count(pair_term)
    if n_pair < 0:
        return f"Could not query PubMed for novelty of {entity_a} <-> {entity_c}."

    lines = [f"Novelty check: {entity_a} <-> {entity_c}"
             + (f"  (bridge: {via})" if via else ""),
             f"  co-mentions of the PAIR in PubMed: {n_pair}"]

    n_bridge = None
    if via:
        bridge_term = f"{pair_term} AND {_q(via)}"
        n_bridge = _pubmed_count(bridge_term)
        lines.append(f"  co-mentions of the A–bridge–C TRIPLE ({via}): {n_bridge}")

    # Classify. When a bridge is given, judge the SPECIFIC mechanism on the triple —
    # a heavily-studied pair can still hide an unpublished gene-mediated link. The
    # pair count is context (is the comorbidity itself known?), not the verdict.
    pair_ctx = "known comorbidity" if n_pair >= ESTABLISHED_N else \
               "lightly co-studied" if n_pair > 0 else "not co-studied"
    if via:
        if n_bridge >= BRIDGE_KNOWN_N:
            status = "bridge_published"
            note = (f"the {via}-mediated link is already established in the "
                    f"literature ({pair_ctx}) — a rediscovery of a known mechanism.")
        elif n_bridge and n_bridge > 0:
            status = "emerging_bridge"
            note = (f"the {via}-mediated link is only lightly studied ({n_bridge} "
                    f"papers; {pair_ctx}) — real but not yet established.")
        elif n_pair >= ESTABLISHED_N:
            status = "novel_bridge"
            note = (f"the comorbidity is well known, but NO paper connects it "
                    f"through {via} — a CANDIDATE mechanism for a known link. "
                    "Novel != correct: run the literature+critic loop before trusting.")
        elif n_pair > 0:
            status = "novel_bridge"
            note = (f"A and C are only lightly co-studied and the {via} bridge is "
                    "absent — a candidate mechanism; verify before trusting.")
        else:
            status = "novel_juxtaposition"
            note = ("neither the pair nor the bridge appears in PubMed — a fully new "
                    "juxtaposition. Novel != correct: calibrate and verify first.")
    else:
        if n_pair >= ESTABLISHED_N:
            status = "established"
            note = ("A and C are already heavily co-studied — surfacing them is a "
                    "REDISCOVERY (validates the method, not a new hypothesis).")
        elif n_pair > 0:
            status = "emerging"
            note = ("A and C are lightly co-studied — give a bridge gene to judge "
                    "whether the specific mechanism is novel.")
        else:
            status = "novel_juxtaposition"
            note = ("the pair does not appear in PubMed — a CANDIDATE new link. "
                    "Novel != correct: calibrate and verify the mechanism first.")

    lines.append(f"  -> {status}: {note}")
    return "\n".join(lines)
