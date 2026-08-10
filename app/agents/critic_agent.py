from collections import Counter
from collections.abc import Sequence

from app.agents.evidence_agent import EvidenceAgent
from app.agents.research_agent import ResearchAgent
from app.evidence.base import EvidenceProviderError
from app.research.search.base import SearchProviderError
from app.rag.retriever import (
    build_index_sources,
    grounded_sources_from_results,
)
from app.schemas.agentic import CriticResult
from app.schemas.evidence import (
    EvidenceItem,
    EvidenceStance,
    ProviderFailure,
)
from app.schemas.investigation import InvestigationSubQuestion
from app.schemas.rag import IndexRequest, RetrievalRequest
from app.schemas.source import Source
from app.services.rag_indexing_service import RAGIndexingService
from app.services.rag_retrieval_service import RAGRetrievalService


class CriticAgent:
    """Run bounded devil's-advocate searches against the leading picture."""

    DEFAULT_MAX_ROUNDS = 1
    HARD_MAX_ROUNDS = 2
    HARD_MAX_SOURCES_PER_QUERY = 3

    def __init__(
        self,
        *,
        research_agent: ResearchAgent,
        evidence_agent: EvidenceAgent,
        rag_indexing_service: RAGIndexingService | None = None,
        rag_retrieval_service: RAGRetrievalService | None = None,
    ) -> None:
        if (rag_indexing_service is None) != (
            rag_retrieval_service is None
        ):
            raise ValueError(
                "Critic RAG indexing and retrieval must be configured together."
            )
        self._research_agent = research_agent
        self._evidence_agent = evidence_agent
        self._rag_indexing_service = rag_indexing_service
        self._rag_retrieval_service = rag_retrieval_service

    async def run(
        self,
        *,
        original_query: str,
        current_evidence: Sequence[EvidenceItem],
        known_sources: Sequence[Source],
        investigation_context: str,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        max_sources_per_query: int = HARD_MAX_SOURCES_PER_QUERY,
        evidence_id_start: int = 1,
    ) -> CriticResult:
        if not 1 <= max_rounds <= self.HARD_MAX_ROUNDS:
            raise ValueError("Critic rounds must be between 1 and 2.")
        if not 1 <= max_sources_per_query <= self.HARD_MAX_SOURCES_PER_QUERY:
            raise ValueError(
                "Critic sources per query must be between 1 and 3."
            )

        target_stance = self._opposing_stance(current_evidence)
        assumptions = [
            "The currently available source set may not be representative.",
            "The leading interpretation may depend on scope, timeframe, or "
            "definitions that do not apply across all sources.",
            "Missing supporting evidence must not be treated as genuine "
            "contradictory evidence.",
        ]
        counter_questions: list[InvestigationSubQuestion] = []
        research_results = []
        new_sources: list[Source] = []
        new_evidence: list[EvidenceItem] = []
        warnings: list[str] = []
        errors: list[ProviderFailure] = []
        known_urls = {str(source.url) for source in known_sources}
        next_source_index = self._next_source_index(known_sources)
        rounds_completed = 0

        for round_number in range(1, max_rounds + 1):
            counter_question = self._counter_question(
                original_query,
                investigation_context,
                target_stance,
                round_number,
            )
            counter_questions.append(counter_question)
            try:
                research_result = await self._research_agent.research(
                    counter_question,
                    max_sources=max_sources_per_query,
                )
            except SearchProviderError as exc:
                errors.append(self._provider_failure(exc))
                warnings.append(
                    "The critic research round stopped after a search "
                    "provider failure; no mock sources were substituted."
                )
                break

            rounds_completed += 1
            research_results.append(research_result)
            unseen_sources = [
                source
                for source in research_result.sources
                if str(source.url) not in known_urls
            ]
            if not unseen_sources:
                warnings.append(
                    "The critic round returned no source URLs beyond the "
                    "already known source set."
                )
                continue

            remapped_sources: list[Source] = []
            for source in unseen_sources:
                remapped = source.model_copy(
                    update={
                        "source_id": f"source-{next_source_index:03d}"
                    }
                )
                next_source_index += 1
                known_urls.add(str(remapped.url))
                remapped_sources.append(remapped)
            new_sources.extend(remapped_sources)

            evidence_sources = remapped_sources
            if self._rag_indexing_service is not None:
                index_result = await self._rag_indexing_service.index(
                    IndexRequest(
                        sources=build_index_sources(remapped_sources)
                    )
                )
                if index_result.failures:
                    warnings.append(
                        "Critic RAG indexing failed; failed source content "
                        "was not sent to evidence extraction."
                    )
                    evidence_sources = []
                else:
                    retrieved = await self._rag_retrieval_service.retrieve(
                        RetrievalRequest(
                            query=counter_question.question,
                            top_k=min(max_sources_per_query * 4, 100),
                            source_ids=[
                                source.source_id
                                for source in remapped_sources
                            ],
                            source_urls=[
                                source.url for source in remapped_sources
                            ],
                        )
                    )
                    evidence_sources = grounded_sources_from_results(
                        remapped_sources,
                        retrieved,
                        limit=max_sources_per_query,
                    )
                if not evidence_sources:
                    warnings.append(
                        "Critic RAG retrieval returned no validated grounded "
                        "chunks; no original source text was substituted."
                    )

            evidence_result = await self._evidence_agent.extract(
                original_query,
                counter_question,
                evidence_sources,
                evidence_id_start=evidence_id_start + len(new_evidence),
            )
            new_evidence.extend(evidence_result.evidence_items)
            warnings.extend(evidence_result.warnings)
            errors.extend(
                self._provider_failure(failure.error)
                for failure in evidence_result.failures
            )

        opposing_ids = [
            item.evidence_id
            for item in new_evidence
            if item.stance is target_stance
        ]
        if opposing_ids:
            finding_summary = (
                "The bounded critic search identified new source-grounded "
                f"evidence classified as {target_stance.value}."
            )
        else:
            finding_summary = (
                "The bounded critic search found no new genuine opposing "
                "evidence. This is an evidence gap, not contradictory or "
                "confirming evidence."
            )

        return CriticResult(
            status="partial" if errors else "completed",
            enabled=True,
            rounds_requested=max_rounds,
            rounds_completed=rounds_completed,
            counter_questions=counter_questions,
            assumptions_challenged=assumptions,
            research_results=research_results,
            new_sources=new_sources,
            new_evidence_items=new_evidence,
            opposing_evidence_ids=opposing_ids,
            finding_summary=finding_summary,
            warnings=warnings,
            errors=errors,
        )

    @staticmethod
    def skipped() -> CriticResult:
        return CriticResult(
            status="skipped",
            enabled=False,
            rounds_requested=0,
            rounds_completed=0,
            counter_questions=[],
            assumptions_challenged=[],
            research_results=[],
            new_sources=[],
            new_evidence_items=[],
            opposing_evidence_ids=[],
            finding_summary=(
                "The devil's-advocate workflow was disabled for this request."
            ),
            warnings=[],
            errors=[],
        )

    @staticmethod
    def _opposing_stance(
        evidence_items: Sequence[EvidenceItem],
    ) -> EvidenceStance:
        counts = Counter(item.stance for item in evidence_items)
        if counts[EvidenceStance.CONTRADICTS] > counts[EvidenceStance.SUPPORTS]:
            return EvidenceStance.SUPPORTS
        return EvidenceStance.CONTRADICTS

    @staticmethod
    def _counter_question(
        query: str,
        context: str,
        target_stance: EvidenceStance,
        round_number: int,
    ) -> InvestigationSubQuestion:
        direction = (
            "supports or materially qualifies"
            if target_stance is EvidenceStance.SUPPORTS
            else "contradicts or materially weakens"
        )
        return InvestigationSubQuestion(
            id=f"sq-{90 + round_number:02d}",
            question=(
                f"What reliable source-grounded evidence {direction} the "
                f"current interpretation of {query!r}?"
            ),
            purpose=(
                "Bounded devil's-advocate research round "
                f"{round_number}; investigation context: {context[:200]}"
            ),
            priority=round_number,
        )

    @staticmethod
    def _next_source_index(sources: Sequence[Source]) -> int:
        indexes = [
            int(source.source_id.rsplit("-", maxsplit=1)[-1])
            for source in sources
        ]
        return max(indexes, default=0) + 1

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
