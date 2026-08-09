import asyncio
from typing import Any, ClassVar

from app.ai.base import LLMProvider
from app.ai.prompts import build_investigation_planning_prompt
from app.schemas.investigation import (
    AIAssumption,
    AIInvestigationPlan,
    AIResearchObjective,
    ExpectedEvidenceType,
    InvestigationDepth,
    InvestigationRequest,
    PotentialBias,
)
from app.services.investigation_service import InvestigationPlanner


class MockLLMProvider(LLMProvider):
    _ASSUMPTION_COUNTS: ClassVar[dict[InvestigationDepth, int]] = {
        InvestigationDepth.QUICK: 1,
        InvestigationDepth.STANDARD: 2,
        InvestigationDepth.DEEP: 4,
    }
    _EVIDENCE_TYPE_COUNTS: ClassVar[dict[InvestigationDepth, int]] = {
        InvestigationDepth.QUICK: 3,
        InvestigationDepth.STANDARD: 4,
        InvestigationDepth.DEEP: 5,
    }
    _BIAS_COUNTS: ClassVar[dict[InvestigationDepth, int]] = {
        InvestigationDepth.QUICK: 2,
        InvestigationDepth.STANDARD: 3,
        InvestigationDepth.DEEP: 4,
    }

    def __init__(
        self,
        model_name: str = "mock-investigator",
        planner: InvestigationPlanner | None = None,
    ) -> None:
        self._model_name = model_name
        self._planner = planner or InvestigationPlanner()
        self.last_prompt: str | None = None

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_investigation_plan(
        self,
        query: str,
        depth: InvestigationDepth,
    ) -> dict[str, Any]:
        self.last_prompt = build_investigation_planning_prompt(query, depth)
        await asyncio.sleep(0)

        request = InvestigationRequest(query=query, depth=depth)
        deterministic_plan = self._planner.plan(request)
        plan = AIInvestigationPlan(
            **deterministic_plan.model_dump(),
            research_objective=AIResearchObjective(
                objective=(
                    "Build a balanced, evidence-aware assessment of "
                    f'"{request.query}" without assuming the conclusion.'
                ),
                success_criteria=[
                    "Define the investigation scope and key terms.",
                    "Compare supporting and contradicting evidence.",
                    "Make uncertainty, limitations, and source quality explicit.",
                ],
            ),
            assumptions=self._build_assumptions(request),
            expected_evidence_types=self._build_evidence_types(depth),
            potential_biases=self._build_potential_biases(depth),
        )
        return plan.model_dump(mode="json")

    def _build_assumptions(
        self,
        request: InvestigationRequest,
    ) -> list[AIAssumption]:
        statements = [
            (
                "The key terms in the query can be defined consistently enough "
                "to support a bounded investigation."
            ),
            (
                "Independent evidence relevant to the query is available for "
                "comparison."
            ),
            (
                "The investigation timeframe can be established from the query "
                "or clarified during research."
            ),
            (
                "Conflicting sources can be evaluated using transparent "
                "credibility criteria."
            ),
        ]
        count = self._ASSUMPTION_COUNTS[request.depth]
        return [
            AIAssumption(
                id=f"assumption-{index:02d}",
                statement=statement,
                requires_validation=True,
            )
            for index, statement in enumerate(statements[:count], start=1)
        ]

    def _build_evidence_types(
        self,
        depth: InvestigationDepth,
    ) -> list[ExpectedEvidenceType]:
        evidence_types = [
            (
                "primary_sources",
                "Original records, documents, datasets, or direct observations.",
            ),
            (
                "authoritative_statistics",
                "Official or methodologically transparent quantitative data.",
            ),
            (
                "peer_reviewed_research",
                "Research with disclosed methods, limitations, and review.",
            ),
            (
                "independent_expert_analysis",
                "Analysis from qualified experts without direct conflicts.",
            ),
            (
                "contemporaneous_reporting",
                "Time-relevant reporting that can establish chronology.",
            ),
        ]
        count = self._EVIDENCE_TYPE_COUNTS[depth]
        return [
            ExpectedEvidenceType(
                evidence_type=evidence_type,
                description=description,
                priority=priority,
            )
            for priority, (evidence_type, description) in enumerate(
                evidence_types[:count],
                start=1,
            )
        ]

    def _build_potential_biases(
        self,
        depth: InvestigationDepth,
    ) -> list[PotentialBias]:
        biases = [
            PotentialBias(
                bias="confirmation_bias",
                risk="Evidence may be selected because it supports an early view.",
                mitigation="Search explicitly for disconfirming evidence.",
            ),
            PotentialBias(
                bias="source_selection_bias",
                risk="Convenient or prominent sources may be overrepresented.",
                mitigation="Use predefined source-quality and diversity criteria.",
            ),
            PotentialBias(
                bias="recency_bias",
                risk="Recent information may overshadow relevant historical evidence.",
                mitigation="Evaluate evidence across an appropriate timeline.",
            ),
            PotentialBias(
                bias="availability_bias",
                risk="Easily accessible evidence may appear more representative.",
                mitigation="Record evidence gaps and inaccessible source classes.",
            ),
        ]
        return biases[: self._BIAS_COUNTS[depth]]
