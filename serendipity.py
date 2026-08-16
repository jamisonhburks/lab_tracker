"""serendipity — surprising, RELEVANT connections you didn't go looking for.

The lab is the source of serendipity: your work meeting other people's, latent KG bridges between
your own entities, active hypotheses that touch your interests. Low-frequency + DEDUPED (each nudge
is shown once, tracked per user) so it delights instead of spamming. Read-only composition of
existing signals + a tiny per-user "seen" set.

Nudge types:
  cluster       — one of YOUR findings shares an entity with a COLLEAGUE's finding (social)
  resurfacing   — your entity just gained a NEW neighbor in someone's consensus/WIP edge
  collaborator  — an active hypothesis touches one of your entities (potential overlap)
  bridge        — two of YOUR entities connect through a KG bridge you may not have noticed (deep)

Cheap nudges (cluster/resurfacing/collaborator) are pure file reads — used in the warm-start
briefing. `bridge` traverses the KG, so it's opt-in (`deep=True`) via the `serendipity` tool.
"""
import itertools
import json
import os
from pathlib import Path

MEM = Path(__file__).parent / "memory"
CONTRIB = MEM / "lab_contributions.jsonl"
MISC = MEM / "misc_findings.jsonl"
HYP = MEM.parent / "hypotheses"
SEEN = MEM / "serendipity_seen.json"


def _who(contributor):
    return contributor or os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "you"


def _jsonl(p):
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()] if p.exists() else []


def _seen(who) -> set:
    try:
        return set(json.loads(SEEN.read_text(encoding="utf-8")).get(who, []))
    except Exception:
        return set()


def _mark(who, keys):
    d = {}
    try:
        d = json.loads(SEEN.read_text(encoding="utf-8"))
    except Exception:
        pass
    d[who] = sorted(set(d.get(who, [])) | set(keys))
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    try:
        SEEN.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def _my_entities(who) -> set:
    return {r[k].lower() for r in _jsonl(CONTRIB) + _jsonl(MISC) if r.get("contributor") == who
            for k in ("subject", "object") if r.get(k)}


def _cluster_nudges(who, my_ents):
    misc = _jsonl(MISC)
    mine = [m for m in misc if m.get("contributor") == who]
    others = [m for m in misc if m.get("contributor") and m.get("contributor") != who]
    out = []
    for m in mine:
        me = {m.get("subject", "").lower(), m.get("object", "").lower()} - {""}
        for o in others:
            shared = me & ({o.get("subject", "").lower(), o.get("object", "").lower()} - {""})
            if shared:
                e = sorted(shared)[0]
                out.append((f"cluster:{e}:{o['contributor']}",
                            f"Shared thread — your \"{m['claim'][:48]}\" and {o['contributor']}'s "
                            f"\"{o['claim'][:48]}\" both touch {e}. A joint hypothesis? "
                            "(group_misc_findings → formalize_misc_group)"))
    return out


def _resurfacing_nudges(who, my_ents):
    out = []
    for c in _jsonl(CONTRIB):
        if c.get("contributor") == who or c.get("status") not in ("auto_merged", "pending_review"):
            continue
        s, o = c.get("subject", "").lower(), c.get("object", "").lower()
        if s in my_ents and o and o not in my_ents:
            you, new = c["subject"], c["object"]
        elif o in my_ents and s and s not in my_ents:
            you, new = c["object"], c["subject"]
        else:
            continue
        out.append((f"resurf:{you.lower()}:{new.lower()}",
                    f"New neighbor — your {you} just connected to {new} in "
                    f"{c.get('contributor', '?')}'s edge. A lead you didn't go looking for."))
    return out


def _collaborator_nudges(who, my_ents):
    import re
    out = []
    if not HYP.exists():
        return out
    for f in sorted(HYP.glob("*.y*ml")):
        try:
            text = f.read_text(encoding="utf-8").lower()
        except Exception:
            continue
        for e in my_ents:                             # word-boundary so short gene symbols (IL6) match safely
            if len(e) >= 2 and re.search(r"\b" + re.escape(e) + r"\b", text):
                out.append((f"hyp:{f.stem}:{e}",
                            f"Overlap — active hypothesis {f.stem.split('_')[0]} touches your "
                            f"{e}. Worth comparing notes. (list_active_work)"))
                break
    return out


def _bridge_nudges(who, my_ents):
    out = []
    ents = [e for e in my_ents if len(e) >= 3][:6]     # include short gene symbols (IL6, MYC)
    try:
        import kg_memory as kg
    except Exception:
        return out
    for a, c in list(itertools.combinations(ents, 2))[:4]:
        try:
            aid, cid, paths, _ = kg.enumerate_paths(a, c, max_len=2)
            if aid and cid and paths:
                p = paths[0]
                seq = [p[0][0]] + [e[4] for e in p]
                bridge = kg._label(seq[1]) if len(seq) >= 3 else None
                if bridge:
                    out.append((f"bridge:{a}:{c}",
                                f"Latent link — your {a} and {c} connect via {bridge} in the KG. "
                                "A mechanism you might not have noticed. (find_paths)"))
        except Exception:
            pass
    return out


def _cold_start_nudges(who):
    """For a user with no history yet: surface what's in flight (active hypotheses) + one open
    frontier cell, so day 1 delights instead of showing nothing. Cheap (hypothesis + profile reads)."""
    import re
    out = []
    for f in (sorted(HYP.glob("*.y*ml")) if HYP.exists() else [])[:3]:
        title, hid = "", f.stem.split("_")[0]
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*title\s*:\s*(.+)", line)
                if m:
                    title = m.group(1).strip().strip('"\''); break
        except Exception:
            pass
        out.append((f"active:{f.stem}",
                    f"In flight — hypothesis {hid}" + (f': "{title[:56]}"' if title else "")
                    + ". See what the lab's working on. (list_active_work)"))
    try:                                          # one open-frontier cell as a latent nudge
        import lab_profile
        sc, cov = lab_profile.scope(), lab_profile.covered()
        covered_pairs = set(cov.get("pairs", []))
        for m, t in [(m, t) for m in sc["modalities"] for t in sc["tasks"]
                     if (m, t) not in covered_pairs][:1]:
            out.append((f"frontier:{m}:{t}",
                        f"Open frontier — the lab works on {m} and {t} but hasn't joined them. "
                        "An unopened cell worth a look. (coverage_map)"))
    except Exception:
        pass
    return out


def nudges(contributor=None, max_nudges: int = 3, deep: bool = False, mark: bool = True) -> list:
    """Up to `max_nudges` fresh serendipity nudges for a researcher (deduped vs already-shown).
    `deep=True` adds KG-bridge nudges (traverses the graph). A brand-new user with no history yet
    is seeded from active work + the lab frontier, so day 1 isn't blank. One-line strings."""
    who = _who(contributor)
    my_ents = _my_entities(who)
    if not my_ents:
        cands = _cold_start_nudges(who)
    else:
        cands = (_cluster_nudges(who, my_ents) + _resurfacing_nudges(who, my_ents)
                 + _collaborator_nudges(who, my_ents))
        if deep:
            cands += _bridge_nudges(who, my_ents)
    seen = _seen(who)
    picked, out, keys = set(), [], []
    for k, t in cands:
        if k in seen or k in picked:
            continue
        picked.add(k); out.append(t); keys.append(k)
        if len(out) >= max_nudges:
            break
    if mark and keys:
        _mark(who, keys)
    return out
