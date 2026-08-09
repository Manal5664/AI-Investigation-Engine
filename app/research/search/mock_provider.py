import asyncio
from datetime import UTC, datetime

from app.research.search.base import SearchProvider
from app.schemas.research import SearchResult
from app.schemas.source import SourceMetadata, SourceType


class MockSearchProvider(SearchProvider):
    _RETRIEVED_AT = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

    @property
    def provider_name(self) -> str:
        return "mock"

    async def search(
        self,
        query: str,
        max_results: int,
        *,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
    ) -> list[SearchResult]:
        if max_results < 1:
            raise ValueError("max_results must be greater than zero")
        if (
            published_after is not None
            and published_before is not None
            and published_after > published_before
        ):
            raise ValueError(
                "published_after must not be later than published_before"
            )

        await asyncio.sleep(0)
        results = self._build_results(query.strip())
        filtered_results = [
            result
            for result in results
            if self._is_within_date_range(
                result,
                published_after,
                published_before,
            )
        ]
        return filtered_results[:max_results]

    def _build_results(self, query: str) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"Mock systematic review related to {query}",
                url="https://academic.example/review/mock-study",
                snippet=(
                    "A mock systematic review reports evidence consistent with "
                    f"key aspects of {query}, while documenting limitations."
                ),
                source_type=SourceType.ACADEMIC,
                published_at=datetime(2025, 4, 10, tzinfo=UTC),
                retrieved_at=self._RETRIEVED_AT,
                author="Dr. Avery Researcher",
                publisher="Example Academic Review",
                metadata=SourceMetadata(
                    language="en",
                    content_type="journal_article",
                    citation_count=42,
                    has_references=True,
                ),
            ),
            SearchResult(
                title=f"Mock government dataset concerning {query}",
                url="https://government.example/data/mock-series",
                snippet=(
                    "A mock official dataset describes measurable trends "
                    f"relevant to {query} without making a causal conclusion."
                ),
                source_type=SourceType.GOVERNMENT,
                published_at=datetime(2025, 7, 1, tzinfo=UTC),
                retrieved_at=self._RETRIEVED_AT,
                publisher="Example Department of Statistics",
                metadata=SourceMetadata(
                    language="en",
                    content_type="dataset",
                    has_references=True,
                ),
            ),
            SearchResult(
                title=f"Mock official guidance about {query}",
                url="https://organization.example/guidance/mock-brief",
                snippet=(
                    "Mock organizational guidance identifies evidence that "
                    f"supports further investigation of {query}."
                ),
                source_type=SourceType.OFFICIAL_ORGANIZATION,
                published_at=datetime(2024, 11, 20, tzinfo=UTC),
                retrieved_at=self._RETRIEVED_AT,
                author="Evidence Standards Team",
                publisher="Example Standards Organization",
                metadata=SourceMetadata(
                    language="en",
                    content_type="guidance",
                    has_references=True,
                ),
            ),
            SearchResult(
                title=f"Mock independent reporting challenging {query}",
                url="https://news.example/investigations/mock-report",
                snippet=(
                    "Mock independent reporting documents observations that "
                    f"challenge common assumptions about {query}."
                ),
                source_type=SourceType.NEWS,
                published_at=datetime(2026, 2, 15, tzinfo=UTC),
                retrieved_at=self._RETRIEVED_AT,
                author="Jordan Reporter",
                publisher="Example Independent News",
                metadata=SourceMetadata(
                    language="en",
                    content_type="news_article",
                    has_references=False,
                ),
            ),
            SearchResult(
                title=f"Mock reference overview for {query}",
                url="https://reference.example/topics/mock-overview",
                snippet=(
                    "A mock reference overview defines terminology and "
                    f"historical context for {query} without taking a position."
                ),
                source_type=SourceType.REFERENCE,
                published_at=datetime(2023, 6, 5, tzinfo=UTC),
                retrieved_at=self._RETRIEVED_AT,
                publisher="Example Reference Library",
                metadata=SourceMetadata(
                    language="en",
                    content_type="reference_entry",
                    has_references=True,
                ),
            ),
            SearchResult(
                title=f"Mock expert blog commentary on {query}",
                url="https://blog.example/posts/mock-commentary",
                snippet=(
                    "A mock commentary offers an interpretation of "
                    f"{query}, but provides limited supporting documentation."
                ),
                source_type=SourceType.BLOG,
                published_at=datetime(2025, 9, 12, tzinfo=UTC),
                retrieved_at=self._RETRIEVED_AT,
                author="Casey Commentator",
                publisher="Example Analysis Blog",
                metadata=SourceMetadata(
                    language="en",
                    content_type="blog_post",
                    has_references=False,
                ),
            ),
            SearchResult(
                title=f"Mock social discussion mentioning {query}",
                url="https://social.example/posts/mock-thread",
                snippet=(
                    "A mock social-media discussion mentions "
                    f"{query} but contains no independently checkable evidence."
                ),
                source_type=SourceType.SOCIAL_MEDIA,
                published_at=None,
                retrieved_at=self._RETRIEVED_AT,
                author="Example User",
                publisher="Example Social Platform",
                metadata=SourceMetadata(
                    language="en",
                    content_type="social_post",
                    has_references=False,
                ),
            ),
            SearchResult(
                title=f"Mock unattributed page concerning {query}",
                url="https://unknown.example/mock-page",
                snippet=(
                    "A mock unattributed page makes assertions about "
                    f"{query} without author, date, or references."
                ),
                source_type=SourceType.UNKNOWN,
                published_at=None,
                retrieved_at=self._RETRIEVED_AT,
                metadata=SourceMetadata(
                    language="en",
                    content_type="web_page",
                    has_references=False,
                ),
            ),
        ]

    @staticmethod
    def _is_within_date_range(
        result: SearchResult,
        published_after: datetime | None,
        published_before: datetime | None,
    ) -> bool:
        if published_after is not None:
            if result.published_at is None or result.published_at < published_after:
                return False
        if published_before is not None:
            if result.published_at is None or result.published_at > published_before:
                return False
        return True
