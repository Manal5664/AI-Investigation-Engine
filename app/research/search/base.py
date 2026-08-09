from abc import ABC, abstractmethod
from datetime import datetime

from app.core.exceptions import ApplicationError
from app.schemas.research import (
    GroundedSearchResponse,
    SearchResult,
    WebGroundingMetadata,
)


class SearchProviderError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            code="search_provider_error",
            status_code=502,
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
