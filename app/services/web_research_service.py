from app.research.search.base import SearchProvider
from app.schemas.research import (
    GroundingCitation,
    WebResearchResult,
)
from app.schemas.source import CredibilityLevel
from app.services.research_service import ResearchService
from app.services.source_credibility_service import SourceCredibilityService


class WebResearchService:
    """Normalize and assess grounded sources without extracting evidence."""

    def __init__(
        self,
        search_provider: SearchProvider,
        credibility_service: SourceCredibilityService | None = None,
    ) -> None:
        self._search_provider = search_provider
        self._credibility_service = (
            credibility_service or SourceCredibilityService()
        )

    async def research(
        self,
        query: str,
        *,
        max_results: int,
    ) -> WebResearchResult:
        grounded_response = (
            await self._search_provider.search_with_context(
                query,
                max_results,
            )
        )
        normalized_sources = ResearchService.normalize_sources(
            grounded_response.results
        )
        sources = [
            source.model_copy(
                update={
                    "credibility": self._credibility_service.assess(source)
                }
            )
            for source in normalized_sources
        ]
        source_ids_by_url = {
            str(source.url): source.source_id
            for source in sources
        }
        citations: list[GroundingCitation] = []
        dropped_citations = 0
        for citation in grounded_response.grounding_metadata.citations:
            source_id = source_ids_by_url.get(str(citation.source_url))
            if source_id is None:
                dropped_citations += 1
                continue
            citations.append(
                citation.model_copy(update={"source_id": source_id})
            )

        warnings = list(grounded_response.warnings)
        warnings.append(
            "Credibility ratings are source-quality heuristics only and do "
            "not establish whether any claim is true."
        )
        low_quality_count = sum(
            source.credibility is not None
            and source.credibility.level
            in {CredibilityLevel.LOW, CredibilityLevel.UNKNOWN}
            for source in sources
        )
        if low_quality_count:
            warnings.append(
                f"{low_quality_count} grounded source(s) received low or "
                "unknown source-quality ratings."
            )
        if dropped_citations:
            warnings.append(
                f"Dropped {dropped_citations} citation(s) that did not map "
                "to a normalized grounded source."
            )

        return WebResearchResult(
            query=grounded_response.query,
            provider_used=grounded_response.provider_used,
            model_used=grounded_response.model_used,
            sources=sources,
            grounded_summary=grounded_response.grounded_summary,
            grounding_metadata=(
                grounded_response.grounding_metadata.model_copy(
                    update={"citations": citations}
                )
            ),
            warnings=warnings,
        )
