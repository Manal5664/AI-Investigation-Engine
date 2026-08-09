from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


QueryText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=5),
]


class InvestigationDepth(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class InvestigationCategory(str, Enum):
    FACTUAL_CLAIM = "factual_claim"
    COMPARISON = "comparison"
    CAUSAL_QUESTION = "causal_question"
    RESEARCH_TOPIC = "research_topic"
    CURRENT_EVENT = "current_event"
    GENERAL_INVESTIGATION = "general_investigation"


class ResearchAngleType(str, Enum):
    SUPPORTING_EVIDENCE = "supporting_evidence"
    CONTRADICTING_EVIDENCE = "contradicting_evidence"
    SOURCE_CREDIBILITY = "source_credibility"
    HISTORICAL_CONTEXT = "historical_context"
    LIMITATIONS = "limitations"
    ALTERNATIVE_EXPLANATIONS = "alternative_explanations"
    DEFINITIONS_AND_SCOPE = "definitions_and_scope"
    RECENT_DEVELOPMENTS = "recent_developments"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvestigationRequest(StrictModel):
    query: QueryText
    depth: InvestigationDepth = InvestigationDepth.STANDARD


class ResearchAngle(StrictModel):
    angle: ResearchAngleType
    description: str = Field(min_length=1)


class InvestigationSubQuestion(StrictModel):
    id: str = Field(pattern=r"^sq-\d{2}$")
    question: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    priority: int = Field(ge=1)


class InvestigationPlan(StrictModel):
    query: QueryText
    depth: InvestigationDepth
    category: InvestigationCategory
    research_angles: list[ResearchAngle] = Field(min_length=1)
    sub_questions: list[InvestigationSubQuestion] = Field(min_length=1)


class AIResearchObjective(StrictModel):
    objective: str = Field(min_length=1)
    success_criteria: list[str] = Field(min_length=1)


class AIAssumption(StrictModel):
    id: str = Field(pattern=r"^assumption-\d{2}$")
    statement: str = Field(min_length=1)
    requires_validation: bool


class ExpectedEvidenceType(StrictModel):
    evidence_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: int = Field(ge=1)


class PotentialBias(StrictModel):
    bias: str = Field(min_length=1)
    risk: str = Field(min_length=1)
    mitigation: str = Field(min_length=1)


class AIInvestigationPlan(InvestigationPlan):
    research_objective: AIResearchObjective
    assumptions: list[AIAssumption] = Field(min_length=1)
    expected_evidence_types: list[ExpectedEvidenceType] = Field(min_length=1)
    potential_biases: list[PotentialBias] = Field(min_length=1)


class InvestigationResponse(StrictModel):
    status: Literal["investigation_planned"]
    plan: AIInvestigationPlan | InvestigationPlan


class AIInvestigationResponse(InvestigationResponse):
    provider_used: str = Field(min_length=1)
    model_used: str = Field(min_length=1)
    fallback_used: bool
    provider_error: str | None = None
