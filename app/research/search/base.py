from abc import ABC, abstractmethod
from datetime import datetime

from app.core.exceptions import ApplicationError
from app.schemas.research import (
    GroundedSearchResponse,
    SearchResult,
    WebGroundingMetadata,
)


class SearchProviderError(ApplicationError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str = "provider_error",
        provider: str = "unknown",
        model: str = "unknown",
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(
            message,
            code="search_provider_error",
            status_code=502,
        )
        self.error_type = error_type
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class SearchProviderRateLimitError(SearchProviderError):
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(
            "Gemini grounded search is temporarily unavailable because the "
            "API quota or rate limit was exhausted. Please try again later.",
            error_type="rate_limit",
            provider=provider,
            model=model,
            retryable=True,
            retry_after_seconds=retry_after_seconds,
        )


class SearchProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable provider identifier."""

    @property
    def model_name(self) -> str:
        """Return the model identifier, if the provider uses one."""
        return "not_applicable"

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
    ) -> list[SearchResult]:
        """Return typed search results without normalizing them into sources."""

    async def search_with_context(
        self,
        query: str,
        max_results: int,
        *,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
    ) -> GroundedSearchResponse:
        results = await self.search(
            query,
            max_results,
            published_after=published_after,
            published_before=published_before,
        )
        return GroundedSearchResponse(
            query=query,
            provider_used=self.provider_name,
            model_used=self.model_name,
            results=results,
            grounded_summary=None,
            grounding_metadata=WebGroundingMetadata(),
            warnings=[
                "This provider returned search results without grounding "
                "metadata."
            ],
        )

    async def aclose(self) -> None:
        """Release provider resources when the adapter owns any."""
