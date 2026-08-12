# toy-research-agent

A minimal, fully-local research agent: a Qwen3-14B model (via Ollama) in a manual
tool-calling loop. Built to make the agent pattern legible and to keep data on-device.

The loop is: call the model → if it requested a tool, run it and feed the result
back → repeat until it stops. Two grounding tools:

- `search_pubmed` — PubMed abstracts via NCBI E-utilities (no API key). The
  grounding step; swap/supplement with a KB/KG retriever (UMLS/MeSH, Hetionet,
  SPOKE) for stronger biomedical grounding.
- `read_file` — read a local file (e.g. a hypothesis YAML or literature note).

## Setup

```sh
# 1. Install Ollama (https://ollama.com/download), or: brew install ollama && ollama serve
# 2. Pull the model + install the client
ollama pull qwen3:14b
pip install -r requirements.txt
```

## Run

```sh
python agent.py "Search PubMed for ECG deep learning foundation models and summarize the main approaches."
```

## Notes

- First run loads ~9GB into memory; subsequent runs are fast (Metal/MPS GPU).
- `think=False` in `agent.py` keeps responses snappy; set `True` for harder
  "is this novel?" planning.
- Expect well-grounded, verifiable hypotheses — not frontier-level creative leaps.
