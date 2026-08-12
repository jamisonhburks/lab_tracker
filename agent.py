"""A toy research agent running fully locally on a Qwen3-14B model via Ollama.

The agent loop is model-agnostic: call the model -> if it asked for a tool, run
the tool and feed the result back -> repeat until it stops asking for tools.
Nothing here is Ollama-specific except the `ollama.chat(...)` calls.

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

import ollama

import memory
import semantic_memory
import kg_memory as kg

MODEL = "qwen3:14b"
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
]

DISPATCH = {
    "search_pubmed": search_pubmed,
    "read_file": read_file,
    "recall_past_runs": memory.recall_past_runs,
    "search_semantic": semantic_memory.search_semantic,
    "query_graph": kg.query_graph,
    "find_paths": kg.find_paths,
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
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim", "sources"],
            },
        },
    },
    "required": ["findings"],
}


# --------------------------------------------------------------------------- #
# The agent loop.                                                             #
# --------------------------------------------------------------------------- #

def run_agent(question: str) -> None:
    messages = [{"role": "user", "content": question}]
    tool_log = []
    seen = set()   # provenance actually observed this run (PMID:… / file:…)

    for _ in range(MAX_STEPS):
        response = ollama.chat(model=MODEL, messages=messages, tools=TOOLS, think=False)
        msg = response["message"]

        if msg.get("content"):
            print(msg["content"])

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            break

        messages.append(msg)
        for call in tool_calls:
            name = call["function"]["name"]
            args = call["function"]["arguments"]
            print(f"  -> calling {name}({args})")
            output = DISPATCH[name](**args)

            tool_log.append({"name": name, "args": args})
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

            messages.append({"role": "tool", "tool_name": name, "content": output})
    else:
        print("\n[stopped: hit MAX_STEPS]")

    findings = _consolidate(messages, seen)
    entry = memory.record_run(question, tool_log, findings)
    n_src = sum(len(f["sources"]) for f in findings)
    print(f"\n[episodic memory: saved {entry['id']} — "
          f"{len(findings)} claim(s), {n_src} source link(s)]")

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
        "empty list."
    )
    try:
        resp = ollama.chat(
            model=MODEL,
            messages=messages + [{"role": "user", "content": prompt}],
            format=CONSOLIDATION_SCHEMA,
            think=False,
        )
        findings = json.loads(resp["message"]["content"]).get("findings", [])
    except Exception as err:  # keep the toy robust if consolidation hiccups
        print(f"[consolidation failed: {err}]")
        return []

    for f in findings:
        f["sources"] = [s for s in f.get("sources", []) if s in seen]
    return [f for f in findings if f.get("claim")]


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Search PubMed for polygenic risk score deep learning."
    run_agent(q)
