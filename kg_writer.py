"""kg_writer — the agent's OWN writable knowledge graph (the KG curator).

Distinct from the read-only grounding KGs (Hetionet/OptimusKG in kg_memory): this
is where the agent PERSISTS associations it extracts from the literature, with
provenance and evidence, so its knowledge compounds across runs. This realizes
"the agent's own written ontological memory" from the architecture doc.

Records are plain JSON dicts (robust storage); reconstruct a typed
kg_schema.Association via to_association() when you need epistemic typing or the
confidence scorer. Deduplication MERGES evidence for the same (subject, predicate,
object) triple, so independent sources accumulate — the signal the confidence
scorer weights (and the reason a claim seen in 3 papers outranks one seen once).
"""

import json
from pathlib import Path

import kg_schema
import store_lock

STORE = Path(__file__).parent / "memory" / "curated_kg.jsonl"


def _key(s: str, p: str, o: str) -> tuple:
    return (s.strip().lower(), p.strip().lower(), o.strip().lower())


def _load() -> list:
    if not STORE.exists():
        return []
    with STORE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _save(records: list) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _rec_key(r: dict) -> tuple:
    """Dedup key — prefer canonical node ids, fall back to the raw text."""
    return (r.get("subject_id") or r["subject"].strip().lower(),
            r["predicate"].strip().lower(),
            r.get("object_id") or r["object"].strip().lower())


def add_association(subject: str, predicate: str, object: str, source: str = "",
                    direction: str = "supports", power: float | None = None,
                    sample_size: int | None = None, effect_size: float | None = None,
                    p_value: float | None = None, risk_of_bias: str | None = None,
                    subject_id: str | None = None, object_id: str | None = None) -> dict:
    """Record an association, or MERGE evidence into an existing one. Returns it.

    Dedup is by CANONICAL node id when available, so surface variants that
    normalize to the same node ('ulcerative colitis (UC)' vs 'ulcerative colitis')
    merge into one association and their evidence accumulates.
    """
    key = (subject_id or subject.strip().lower(), predicate.strip().lower(),
           object_id or object.strip().lower())
    ev = {"source": source or None, "direction": direction, "power": power,
          "sample_size": sample_size, "effect_size": effect_size, "p_value": p_value,
          "risk_of_bias": risk_of_bias}

    with store_lock.critical(STORE):              # lock the whole load→modify→save (shared-safe)
        records = _load()
        for r in records:
            if _rec_key(r) == key:
                r["evidence"].append(ev)          # accumulate independent evidence
                _save(records)
                return r
        record = {
            "subject": subject.strip(), "subject_id": subject_id,
            "predicate": predicate.strip(),
            "object": object.strip(), "object_id": object_id,
            "epistemic_type": kg_schema.classify_epistemic(predicate).value,
            "evidence": [ev],
        }
        records.append(record)
        _save(records)
        return record


def to_association(record: dict) -> "kg_schema.Association":
    """Reconstruct a typed Association from a stored record (for confidence scoring)."""
    evidence = []
    for e in record.get("evidence", []):
        d = e.get("direction", "supports")
        rob = e.get("risk_of_bias")
        evidence.append(kg_schema.Evidence(
            source=e.get("source"),
            direction=kg_schema.Direction(d if d in ("supports", "refutes") else "supports"),
            power=e.get("power"), sample_size=e.get("sample_size"),
            effect_size=e.get("effect_size"), p_value=e.get("p_value"),
            risk_of_bias=kg_schema.RiskOfBias(rob) if rob in ("low", "some", "high") else None,
        ))
    assoc = kg_schema.lift_edge(record["subject"], record["predicate"], record["object"])
    assoc.evidence = evidence
    return assoc


def query(subject: str | None = None, object: str | None = None) -> list:
    """Return stored records matching subject and/or object (case-insensitive substring)."""
    out = []
    for r in _load():
        if subject and subject.lower() not in r["subject"].lower():
            continue
        if object and object.lower() not in r["object"].lower():
            continue
        out.append(r)
    return out
