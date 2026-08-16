"""onboarding — a new lab member's first-session intake STATE (what's set up, what's still missing).

The intake CONVERSATION is driven by a thinker (a Claude session) following
`lab-standard/onboarding.md`. This module is the substrate side: for a given member it reports which
onboarding pieces are already in place vs empty, so the agent asks ONLY for what's missing — never
re-interrogating — and a member can finish onboarding across sessions. Deliberately tiny and
LLM-free; every source is best-effort so a missing subsystem degrades to 0, never an error.

The point of the split: keeping this here lets the intake stay SHORT. The agent glances at the
checklist, skips the ✓ items, and asks one light question for each ○. That is the whole
anti-overwhelm mechanism.
"""

import os


def _who(member=None) -> str:
    return member or os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "you"


def _next_step(s: dict) -> str:
    if not s["in_roster"]:
        return "add you to the lab roster (add_member) — start here."
    if s["n_publications"] == 0:
        return "record a few of your papers (import_publications.py / record_publication) so the coverage map knows your work."
    if s["n_following"] == 0:
        return "follow a colleague or a project you care about (follow)."
    if s["n_topics_seeded"] == 0:
        return "pre-warm one topic you work on (curate_literature) so the KG has your area."
    return "you're set up — dive in (warm_start)."


def status(member=None) -> dict:
    """What's set up for `member` vs missing. `complete` = the three basics (roster + a paper + a
    follow); pre-warmed topics are a bonus. Every lookup is best-effort."""
    who = _who(member)
    s = {"member": who, "in_roster": False, "n_publications": 0, "n_following": 0,
         "n_active_projects": 0, "n_topics_seeded": 0}
    try:
        import lab_profile
        s["in_roster"] = who in lab_profile.roster()
        s["n_publications"] = len(lab_profile.publications(member=who))
    except Exception:
        pass
    try:
        import subscriptions
        s["n_following"] = len(subscriptions.subscriptions_of(who))
    except Exception:
        pass
    try:
        import worklog
        s["n_active_projects"] = len(worklog.active_hypotheses())     # lab context, not owner-scoped
    except Exception:
        pass
    try:
        import deep_search
        s["n_topics_seeded"] = len({e.get("topic") for e in deep_search._cache()
                                    if e.get("contributor") == who and e.get("topic")})
    except Exception:
        pass
    s["complete"] = s["in_roster"] and s["n_publications"] > 0 and s["n_following"] > 0
    s["next"] = _next_step(s)
    return s


def render(member=None) -> str:
    """A compact, glanceable checklist (kept short on purpose — this is the anti-overwhelm view)."""
    s = status(member)
    tick = lambda ok: "✓" if ok else "○"
    return "\n".join([
        f"Onboarding — {s['member']}:",
        f"  {tick(s['in_roster'])} on the lab roster",
        f"  {tick(s['n_publications'] > 0)} papers recorded ({s['n_publications']})",
        f"  {tick(s['n_following'] > 0)} following someone ({s['n_following']})",
        f"  {tick(s['n_topics_seeded'] > 0)} topics pre-warmed ({s['n_topics_seeded']})",
        f"→ next: {s['next']}",
    ])


if __name__ == "__main__":
    print(render())
