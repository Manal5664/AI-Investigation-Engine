from collections import Counter

from app.evidence.base import EvidenceExtractor, EvidenceProviderError
from app.research.search.base import (
    SearchProvider,
    SearchProviderError,
    SearchProviderRateLimitError,
)
from app.schemas.evidence import (
    EvidenceItem,
    EvidenceStance,
    EvidenceStanceCounts,
    ProviderFailure,
)
from app.schemas.investigation import InvestigationRequest
from app.schemas.research import (
    InvestigationQuestionResearchResult,
    InvestigationResearchRequest,
    InvestigationResearchResponse,
)
from app.services.evidence_conflict_service import EvidenceConflictService
from app.services.evidence_summary_service import EvidenceSummaryService
from app.services.investigation_service import InvestigationPlanner
from app.services.web_research_service import WebResearchService


class InvestigationResearchService:
    def __init__(
        self,
        *,
        search_provider: SearchProvider,
        evidence_extractor: EvidenceExtractor,
        planner: InvestigationPlanner | None = None,
        conflict_service: EvidenceConflictService | None = None,
        summary_service: EvidenceSummaryService | None = None,
    ) -> None:
        self._search_provider = search_provider
        self._evidence_extractor = evidence_extractor
        self._planner = planner or InvestigationPlanner()
        self._conflict_service = (
            conflict_service or EvidenceConflictService()
        )
        self._summary_service = summary_service or EvidenceSummaryService()

    async def research(
        self,
        request: InvestigationResearchRequest,
    ) -> InvestigationResearchResponse:
        plan = self._planner.plan(
            InvestigationRequest(query=request.query, depth=request.depth)
        )
        selected_questions = sorted(
            plan.sub_questions,
            key=lambda question: question.priority,
        )[: request.max_sub_questions]
        web_service = WebResearchService(self._search_provider)
        question_results: list[InvestigationQuestionResearchResult] = []
        all_evidence: list[EvidenceItem] = []
        conflicts = []
        warnings = [
            "Cost controls limited this run to at most "
            f"{request.max_sub_questions} sub-question(s) and "
            f"{request.max_sources_per_question} source(s) per question."
        ]
        if self._evidence_extractor.provider_name == "mock":
            warnings.append(
                "The mock evidence extractor was explicitly configured for "
                "development; source retrieval was not replaced with mock "
                "sources."
            )

        failure: ProviderFailure | None = None
        for sub_question in selected_questions:
            try:
                web_result = await web_service.research(
                    sub_question.question,
                    max_results=request.max_sources_per_question,
                )
            except SearchProviderRateLimitError as exc:
                failure = self._provider_failure(exc)
                warnings.append(
                    "Grounded web research stopped because the Gemini API "
                    "quota/rate limit was unavailable. No mock sources were "
                    "substituted."
                )
                break
            except SearchProviderError as exc:
                failure = self._provider_failure(exc)
                warnings.append(
                    "Grounded web research stopped after a provider failure. "
                    "No mock sources were substituted."
                )
                break

            if web_result.sources:
                try:
                    evidence_items = await self._evidence_extractor.extract(
                        sub_question,
                        web_result.sources,
                        investigation_query=plan.query,
                    )
                except EvidenceProviderError as exc:
                    failure = self._provider_failure(exc)
                    warnings.append(
                        "Evidence extraction stopped after a provider or "
                        "grounding-validation failure."
                    )
                    break
            else:
                evidence_items = []

            evidence_items = self._reindex_evidence(
                evidence_items,
                start=len(all_evidence) + 1,
            )
            all_evidence.extend(evidence_items)
            counts = self._stance_counts(evidence_items)
            conflict_report = self._conflict_service.detect(
                sub_question,
                evidence_items,
            )
            conflicts.append(conflict_report)
            question_warnings = list(web_result.warnings)
            if not web_result.sources:
                question_warnings.append(
                    "No grounded sources were available, so no evidence was "
                    "extracted for this sub-question."
                )
            question_results.append(
                InvestigationQuestionResearchResult(
                    sub_question=sub_question,
                    sources=web_result.sources,
                    grounded_summary=web_result.grounded_summary,
                    evidence_items=evidence_items,
                    stance_counts=counts,
                    conflicts=conflict_report,
                    warnings=question_warnings,
                )
            )

        status = (
            "completed"
            if failure is None
            else "partial"
            if question_results
            else "failed"
        )
        return InvestigationResearchResponse(
            status=status,
            plan=plan,
            search_provider_used=self._search_provider.provider_name,
            search_model_used=self._search_provider.model_name,
            evidence_provider_used=self._evidence_extractor.provider_name,
            evidence_model_used=self._evidence_extractor.model_name,
            question_results=question_results,
            evidence_summary=self._summary_service.summarize_items(
                all_evidence
            ),
            conflicts=conflicts,
            warnings=warnings,
            error=failure,
        )

    @staticmethod
    def _reindex_evidence(
        evidence_items: list[EvidenceItem],
        *,
        start: int,
    ) -> list[EvidenceItem]:
        return [
            item.model_copy(
                update={"evidence_id": f"evidence-{index:03d}"}
            )
            for index, item in enumerate(evidence_items, start=start)
        ]

    @staticmethod
    def _stance_counts(
        evidence_items: list[EvidenceItem],
    ) -> EvidenceStanceCounts:
        counts = Counter(item.stance for item in evidence_items)
        return EvidenceStanceCounts(
            supports=counts[EvidenceStance.SUPPORTS],
            contradicts=counts[EvidenceStance.CONTRADICTS],
            neutral=counts[EvidenceStance.NEUTRAL],
            insufficient=counts[EvidenceStance.INSUFFICIENT],
        )

    @staticmethod
    def _provider_failure(
        exc: SearchProviderError | EvidenceProviderError,
    ) -> ProviderFailure:
        return ProviderFailure(
            error_type=exc.error_type,
            provider=exc.provider,
            model=exc.model,
            message=exc.message,
            retryable=exc.retryable,
            retry_after_seconds=exc.retry_after_seconds,
        )
