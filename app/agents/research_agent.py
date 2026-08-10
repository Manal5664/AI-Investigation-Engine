from app.research.search.base import SearchProvider, SearchProviderError
from app.schemas.investigation import InvestigationSubQuestion
from app.schemas.research import WebResearchResult
from app.services.web_research_service import WebResearchService


class ResearchAgent:
    """Bounded wrapper around grounded web research for one question."""

    MAX_SOURCES_PER_QUESTION = 3

    def __init__(self, search_provider: SearchProvider) -> None:
        self._search_provider = search_provider
        self._service = WebResearchService(search_provider)

    @property
    def provider_name(self) -> str:
        return self._search_provider.provider_name

    @property
    def model_name(self) -> str:
        return self._search_provider.model_name

    async def research(
        self,
        sub_question: InvestigationSubQuestion,
        *,
        max_sources: int,
    ) -> WebResearchResult:
        if not 1 <= max_sources <= self.MAX_SOURCES_PER_QUESTION:
            raise ValueError(
                "Agentic research max_sources must be between 1 and 3."
            )
        result = await self._service.research(
            sub_question.question,
            max_results=max_sources,
        )
        if len(result.sources) > max_sources:
            raise SearchProviderError(
                "Research provider exceeded the requested source limit.",
                error_type="source_limit_violation",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            )
        source_ids = [source.source_id for source in result.sources]
        source_urls = [str(source.url) for source in result.sources]
        if (
            len(source_ids) != len(set(source_ids))
            or len(source_urls) != len(set(source_urls))
        ):
            raise SearchProviderError(
                "Research provider returned duplicate normalized sources.",
                error_type="grounding_validation",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            )
        return result
