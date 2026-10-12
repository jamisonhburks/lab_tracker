"""schemas — Pydantic models for the agent's structured LLM outputs.

These validate what the model *returns* (types, required fields, enums) at the parse
boundary — the flakiest part of any LLM agent. The hand-written JSON schemas in
agent.py / critic.py still drive the model's CONSTRAINED DECODING (unchanged, proven);
these models are the second line: `llm.parse(msgs, SCHEMA, Model)` validates the result
and retries on failure (feeding the error back), so a slightly-off reply is caught and
corrected instead of crashing a `json.loads`.

Optional fields default to None/empty so a valid-but-sparse reply passes; required
fields (claim, verdict, subject/predicate/object, …) trigger a retry if missing.
"""

from typing import Optional

from pydantic import BaseModel, Field


# --- consolidation: claim -> sources findings (agent._consolidate) -------------
class Finding(BaseModel):
    claim: str
    subject: str = ""
    object: str = ""
    sources: list[str] = Field(default_factory=list)


class Consolidation(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


# --- per-paper study extraction (agent.curate_literature) ----------------------
class Association(BaseModel):
    subject: str
    predicate: str
    object: str
    direction: str = "supports"
    sample_size: Optional[int] = None
    effect_size: Optional[float] = None
    p_value: Optional[float] = None
    risk_of_bias: Optional[str] = None


class StudyExtract(BaseModel):
    associations: list[Association] = Field(default_factory=list)


# --- pre-flight tool plan (agent._plan_tools) ----------------------------------
class ToolPlanItem(BaseModel):
    tool: str
    why: str = ""


class ToolPlan(BaseModel):
    intended: list[ToolPlanItem] = Field(default_factory=list)


# --- hybrid hypothesis synthesis (agent.generate_hypothesis) -------------------
class Mechanism(BaseModel):
    intermediate: str = ""
    rationale: str = ""
    centrality: str = ""


class Hypothesis(BaseModel):
    hypothesis: str
    mechanisms: list[Mechanism] = Field(default_factory=list)
    caveats: str = ""


# The 'testable' generation variant (ADR-0063 intervention): same hypothesis, but the
# model must also commit to a refutable prediction and an experiment that tests it.
class HypothesisTestable(Hypothesis):
    falsifiable_prediction: str = ""
    experiment: str = ""


# --- critic verdict (critic.criticize) -----------------------------------------
class Verdict(BaseModel):
    verdict: str
    reason: str = ""
    well_formed: bool = False
    source_supported: bool = False
    type_valid: Optional[bool] = None
    plausible: Optional[bool] = None


# --- campaign next-step proposal (campaign._synthesize) ------------------------
class NextStep(BaseModel):
    title: str
    question: str
    key_change: str
    rationale: str


# --- idea intake: free-text idea -> testable entity pair(s) (idea.assess_idea) -
class IdeaPair(BaseModel):
    entity_a: str
    entity_c: str
    relation: str = ""
    rationale: str = ""


class IdeaExtraction(BaseModel):
    pairs: list[IdeaPair] = Field(default_factory=list)
