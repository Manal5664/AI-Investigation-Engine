from abc import ABC, abstractmethod
from datetime import datetime

from app.schemas.research import SearchResult


class SearchProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable provider identifier."""

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
