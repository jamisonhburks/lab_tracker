"""specialist — a Claude-backed scientific specialist that executes Agent Skills.

The local Qwen orchestrator stays on-device for the privacy-sensitive reasoning (KG,
novelty, memory, hypothesis triage). When a hypothesis needs real scientific
COMPUTATION — cohort tables, survival-analysis plans, biomarker/model evaluation,
de-identification checks, experimental design — it delegates ONE task to this
specialist via `run_specialist()`. The specialist runs on Claude (a frontier model is
needed to follow multi-step SKILL.md procedures and drive their scripts) with three
capabilities:

  - list_skills()             what skills are available (name + description)
  - read_skill(name[, file])  open a skill's SKILL.md or a bundled reference/script
  - run_bash(command)         run a skill's scripts in an isolated workspace

Skills come from the k-dense-ai/scientific-agent-skills library (MIT), mounted from
SPECIALIST_SKILLS_DIR (clone it there — it is not vendored into this repo). A 14B
can't drive 158 skills, but Claude can follow the handful relevant to computational
medicine; SPECIALIST_SKILLS allow-lists that subset so the specialist isn't swamped.

Why Claude here (ADR-0014 rationale, made explicit): this is the execution layer where
frontier tool-use reasoning pays off. The privacy line (ADR-0001) is preserved by
keeping patient-row data on the local side — hand the specialist only de-identified /
aggregate / synthetic inputs (the clinical skills are research-only by design).
"""

import os
import subprocess
from pathlib import Path

import llm

_ROOT = Path(__file__).parent
SKILLS_DIR = Path(os.environ.get(
    "SPECIALIST_SKILLS_DIR", _ROOT / "external" / "scientific-agent-skills" / "skills"))
WORKSPACE = Path(os.environ.get("SPECIALIST_WORKSPACE", _ROOT / "data" / "specialist_workspace"))
# Curated allow-list (computational-medicine relevant). Empty -> expose all found.
SPECIALIST_SKILLS = [s for s in os.environ.get(
    "SPECIALIST_SKILLS",
    "clinical-decision-support,clinical-reports,experimental-design,"
    "exploratory-data-analysis,analytical-method-validation,biopython").split(",") if s]
MAX_STEPS = 14


# --------------------------------------------------------------------------- #
# Skill discovery + the specialist's tools (plain, deterministic).            #
# --------------------------------------------------------------------------- #

def _available() -> list:
    """Skill dirs that exist and (if an allow-list is set) are allow-listed."""
    if not SKILLS_DIR.exists():
        return []
    out = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if (d / "SKILL.md").exists() and (not SPECIALIST_SKILLS or d.name in SPECIALIST_SKILLS):
            out.append(d)
    return out


def _description(skill_dir: Path) -> str:
    """Pull the `description:` line from a SKILL.md YAML frontmatter."""
    try:
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")[:4000]
    except OSError:
        return ""
    for line in text.splitlines():
        if line.strip().startswith("description:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""


def list_skills() -> str:
    skills = _available()
    if not skills:
        return (f"No skills found under {SKILLS_DIR}. Clone the library there: "
                "git clone https://github.com/k-dense-ai/scientific-agent-skills.git "
                f"{SKILLS_DIR.parent}")
    return "Available skills:\n" + "\n".join(
        f"- {d.name}: {_description(d)[:200]}" for d in skills)


def read_skill(name: str, file: str = "SKILL.md") -> str:
    """Read a skill's SKILL.md, or a bundled reference/asset/script (relative path)."""
    base = (SKILLS_DIR / name).resolve()
    target = (base / file).resolve()
    if SKILLS_DIR.resolve() not in target.parents and target != base:  # no path escape
        return "Refused: path outside the skills directory."
    if not target.exists():
        listing = "\n".join(sorted(str(p.relative_to(base)) for p in base.rglob("*")
                                   if p.is_file())[:60]) if base.exists() else ""
        return f"{file} not found in skill {name!r}. Files:\n{listing}"
    return target.read_text(encoding="utf-8", errors="replace")[:20000]


def run_bash(command: str) -> str:
    """Run a shell command in the specialist workspace (for executing skill scripts)."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(command, shell=True, cwd=str(WORKSPACE), capture_output=True,
                           text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "Command timed out (180s)."
    out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
    return (out or "(no output)")[:12000] + (f"\n[exit {p.returncode}]" if p.returncode else "")


SPECIALIST_TOOLS = [
    {"type": "function", "function": {
        "name": "list_skills",
        "description": "List the scientific Agent Skills available to you (name + description).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "read_skill",
        "description": ("Open a skill's SKILL.md (its procedure), or a bundled file "
                        "(reference/asset/script) by relative path. Read SKILL.md "
                        "first, then the references/scripts it points to."),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Skill name, e.g. 'clinical-decision-support'."},
            "file": {"type": "string", "description": "Relative path in the skill; default SKILL.md."}},
            "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "run_bash",
        "description": ("Execute a shell command in your workspace — use to run a "
                        "skill's scripts (e.g. `python <path-to-skill>/scripts/x.py ...`) "
                        "and inspect outputs. Inputs must be de-identified/aggregate."),
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
]

_DISPATCH = {"list_skills": list_skills, "read_skill": read_skill, "run_bash": run_bash}


# --------------------------------------------------------------------------- #
# The specialist agent loop (runs on Claude).                                  #
# --------------------------------------------------------------------------- #

_SYSTEM = (
    "You are a scientific computation specialist for a computational-medicine research "
    "agent. You have a library of Agent Skills (SKILL.md procedures + bundled scripts). "
    "For a task: call list_skills, read the most relevant SKILL.md (and the references/"
    "scripts it cites), then execute its scripts with run_bash and report concrete "
    "results (paths to artifacts, key numbers, and any assumptions). Follow each "
    "skill's safety boundaries exactly. Inputs are de-identified/aggregate/synthetic — "
    "never attempt to re-identify or produce patient-specific clinical decisions. When "
    "done, give a concise result summary, not a play-by-play."
)


def run_specialist(task: str, backend: str = "anthropic") -> str:
    """Delegate one scientific-computation task to the Claude specialist + skills.

    Returns the specialist's final result summary. Runs on Claude regardless of the
    orchestrator's backend (needs frontier tool-use); requires ANTHROPIC_API_KEY and
    the `anthropic` package, and the skills library cloned under SPECIALIST_SKILLS_DIR.
    """
    if not _available():
        return list_skills()          # helpful "clone the library" message
    messages = [{"role": "user", "content": f"{_SYSTEM}\n\nTASK:\n{task}"}]
    transcript = []
    for _ in range(MAX_STEPS):
        try:
            resp = llm.chat(messages, tools=SPECIALIST_TOOLS, backend=backend)
        except Exception as err:       # no key / no SDK / API error — fail gracefully
            return (f"[specialist unavailable: {err}] Set ANTHROPIC_API_KEY and "
                    "`pip install anthropic` to run the Claude specialist.")
        if resp.text:
            transcript.append(resp.text)
        if not resp.tool_calls:
            break
        messages.append({"role": "assistant", "content": resp.text,
                         "tool_calls": [{"id": tc.id, "name": tc.name, "args": tc.args}
                                        for tc in resp.tool_calls]})
        for tc in resp.tool_calls:
            out = _DISPATCH[tc.name](**tc.args) if tc.name in _DISPATCH else f"unknown tool {tc.name}"
            messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name,
                             "content": str(out)})
    return transcript[-1] if transcript else "(specialist returned no summary)"
