from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

from app.evidence.base import EvidenceExtractor
from app.research.search.base import SearchProvider
from app.schemas.evidence import EvidenceStance, EvidenceStanceCounts
from app.schemas.investigation import (
    InvestigationPlan,
    InvestigationSubQuestion,
)
from app.schemas.research import ResearchResult, SearchResult
from app.schemas.source import CredibilityLevel, Source
from app.services.source_credibility_service import SourceCredibilityService


class ResearchService:
    def __init__(
        self,
        search_provider: SearchProvider,
        evidence_extractor: EvidenceExtractor,
        credibility_service: SourceCredibilityService | None = None,
    ) -> None:
        self._search_provider = search_provider
        self._evidence_extractor = evidence_extractor
        self._credibility_service = (
            credibility_service or SourceCredibilityService()
        )

    async def research(
        self,
        plan: InvestigationPlan,
        *,
        sub_question: str | None = None,
        max_results: int = 5,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
    ) -> ResearchResult:
        selected_sub_question = self.select_sub_question(
            plan,
            sub_question,
        )
        search_results = await self._search_provider.search(
            selected_sub_question.question,
            max_results,
            published_after=published_after,
            published_before=published_before,
        )
        sources = self.normalize_sources(search_results)
        assessed_sources = [
            source.model_copy(
                update={
                    "credibility": self._credibility_service.assess(source)
                }
            )
            for source in sources
        ]
        evidence_items = await self._evidence_extractor.extract(
            selected_sub_question,
            assessed_sources,
            investigation_query=plan.query,
        )
        counts = Counter(item.stance for item in evidence_items)

        warnings = [
            (
                "Source credibility scores are explainable source-quality "
                "heuristics; they do not establish whether information is true."
            )
        ]
        low_quality_count = sum(
            source.credibility is not None
            and source.credibility.level
            in {CredibilityLevel.LOW, CredibilityLevel.UNKNOWN}
            for source in assessed_sources
        )
        if low_quality_count:
            warnings.append(
                f"{low_quality_count} source(s) received low or unknown "
                "source-quality ratings."
            )
        if not assessed_sources:
            warnings.append("No search results matched the request.")

        return ResearchResult(
            investigation_query=plan.query,
            depth=plan.depth,
            sub_question=selected_sub_question,
            sources=assessed_sources,
            evidence_items=evidence_items,
            counts_by_stance=EvidenceStanceCounts(
                supports=counts[EvidenceStance.SUPPORTS],
                contradicts=counts[EvidenceStance.CONTRADICTS],
                neutral=counts[EvidenceStance.NEUTRAL],
                insufficient=counts[EvidenceStance.INSUFFICIENT],
            ),
            warnings=warnings,
        )

    @staticmethod
    def select_sub_question(
        plan: InvestigationPlan,
        requested_sub_question: str | None,
    ) -> InvestigationSubQuestion:
        if requested_sub_question is not None:
            return InvestigationSubQuestion(
                id="sq-00",
                question=requested_sub_question.strip(),
                purpose="User-supplied research sub-question.",
                priority=1,
            )
        return plan.sub_questions[0]

    @staticmethod
    def normalize_sources(
        search_results: list[SearchResult],
    ) -> list[Source]:
        sources: list[Source] = []
        for index, result in enumerate(search_results, start=1):
            domain = urlparse(str(result.url)).netloc.casefold()
            sources.append(
                Source(
                    source_id=f"source-{index:03d}",
                    title=result.title,
                    url=result.url,
                    author=result.author,
                    publisher=result.publisher,
                    domain=domain.removeprefix("www."),
                    published_at=result.published_at,
                    retrieved_at=result.retrieved_at,
                    source_type=result.source_type,
                    snippet=result.snippet,
                    metadata=result.metadata,
                )
            )
        return sources
