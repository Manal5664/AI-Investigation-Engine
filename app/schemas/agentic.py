from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from app.schemas.evidence import (
    EvidenceConflictReport,
    EvidenceItem,
    EvidenceStanceCounts,
    ProviderFailure,
)
from app.schemas.investigation import (
    InvestigationDepth,
    InvestigationPlan,
    InvestigationSubQuestion,
    QueryText,
    StrictModel,
)
from app.schemas.research import WebResearchResult
from app.schemas.source import Source


class AgentStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class SynthesisConfidence(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class AgentStep(StrictModel):
    step_id: str = Field(pattern=r"^step-\d{3}$")
    step_name: str = Field(min_length=1)
    status: AgentStepStatus
    started_at: datetime
    completed_at: datetime
    provider_used: str | None = Field(default=None, min_length=1)
    model_used: str | None = Field(default=None, min_length=1)
    action_summary: str = Field(min_length=1)
    input_references: list[str] = Field(default_factory=list)
    output_references: list[str] = Field(default_factory=list)
    source_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    errors: list[ProviderFailure] = Field(default_factory=list)


class AgenticQuestionResult(StrictModel):
    sub_question: InvestigationSubQuestion
    status: Literal["completed", "partial"]
    research: WebResearchResult
    evidence_items: list[EvidenceItem]
    stance_counts: EvidenceStanceCounts
    conflicts: EvidenceConflictReport
    warnings: list[str]
    errors: list[ProviderFailure]


class CriticResult(StrictModel):
    status: Literal["completed", "partial", "skipped"]
    enabled: bool
    rounds_requested: int = Field(ge=0, le=2)
    rounds_completed: int = Field(ge=0, le=2)
    counter_questions: list[InvestigationSubQuestion]
    assumptions_challenged: list[str]
    research_results: list[WebResearchResult]
    new_sources: list[Source]
    new_evidence_items: list[EvidenceItem]
    opposing_evidence_ids: list[str]
    finding_summary: str = Field(min_length=1)
    warnings: list[str]
    errors: list[ProviderFailure]


class SynthesisResult(StrictModel):
    overall_evidence_picture: str = Field(min_length=1)
    strongest_supporting_evidence: EvidenceItem | None = None
    strongest_contradicting_evidence: EvidenceItem | None = None
    unresolved_conflicts: list[str]
    important_limitations: list[str]
    alternative_explanations: list[str]
    evidence_gaps: list[str]
    confidence_level: SynthesisConfidence
    confidence_rationale: str = Field(min_length=1)


class InvestigationState(StrictModel):
    query: QueryText
    depth: InvestigationDepth
    status: Literal["completed", "partial", "failed"]
    plan: InvestigationPlan
    selected_sub_questions: list[InvestigationSubQuestion]
    question_results: list[AgenticQuestionResult]
    critic_result: CriticResult
    conflicts: list[EvidenceConflictReport]
    synthesis: SynthesisResult
    audit_trail: list[AgentStep]
    warnings: list[str]
    errors: list[ProviderFailure]
    total_source_count: int = Field(ge=0)
    total_evidence_count: int = Field(ge=0)


class AgenticInvestigationRequest(StrictModel):
    query: QueryText
    depth: InvestigationDepth = InvestigationDepth.QUICK
    max_sub_questions: int = Field(default=2, ge=1, le=2)
    max_sources_per_question: int = Field(default=3, ge=1, le=3)
    run_critic: bool = True
    max_critic_rounds: int = Field(default=1, ge=1, le=2)
    use_rag: bool = False
    use_graph_rag: bool = False


class AgenticInvestigationResult(StrictModel):
    status: Literal["completed", "partial", "failed"]
    state: InvestigationState
