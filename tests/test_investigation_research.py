import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import ValidationError

from app.evidence.mock_extractor import MockEvidenceExtractor
from app.main import app
from app.research.search.base import (
    SearchProvider,
    SearchProviderRateLimitError,
)
from app.research.search.mock_provider import MockSearchProvider
from app.schemas.research import (
    InvestigationResearchRequest,
    SearchResult,
)
from app.schemas.source import SourceType
from app.services.investigation_research_service import (
    InvestigationResearchService,
)


RETRIEVED_AT = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class StubGroundedSearchProvider(SearchProvider):
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls: list[int] = []
        self._fail_on_call = fail_on_call

    @property
    def provider_name(self) -> str:
        return "gemini_grounded"

    @property
    def model_name(self) -> str:
        return "mocked-grounded-model"

    async def search(
        self,
        query: str,
        max_results: int,
        *,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
    ) -> list[SearchResult]:
        del query, published_after, published_before
        self.calls.append(max_results)
        if self._fail_on_call == len(self.calls):
            raise SearchProviderRateLimitError(
                provider=self.provider_name,
                model=self.model_name,
                retry_after_seconds=12,
            )
        return [
            SearchResult(
                title="Supporting academic source",
                url="https://academic.example/real-source",
                snippet="The supplied study reports improved duration.",
                source_type=SourceType.ACADEMIC,
                retrieved_at=RETRIEVED_AT,
            ),
            SearchResult(
                title="Contradicting news source",
                url="https://news.example/real-source",
                snippet="The supplied report describes lower duration.",
                source_type=SourceType.NEWS,
                retrieved_at=RETRIEVED_AT,
            ),
            SearchResult(
                title="Neutral reference source",
                url="https://reference.example/real-source",
                snippet="The supplied reference defines storage duration.",
                source_type=SourceType.REFERENCE,
                retrieved_at=RETRIEVED_AT,
            ),
        ][:max_results]


def _request(
    *,
    max_sub_questions: int = 1,
    max_sources_per_question: int = 2,
) -> InvestigationResearchRequest:
    return InvestigationResearchRequest(
        query="Research long-duration energy storage performance",
        depth="quick",
        max_sub_questions=max_sub_questions,
        max_sources_per_question=max_sources_per_question,
    )


def test_conflict_detection_finds_opposing_source_claims() -> None:
    search_provider = StubGroundedSearchProvider()
    result = asyncio.run(
        InvestigationResearchService(
            search_provider=search_provider,
            evidence_extractor=MockEvidenceExtractor(),
        ).research(_request())
    )

    conflict = result.question_results[0].conflicts
    assert conflict.has_supporting_and_contradicting_evidence is True
    assert len(conflict.conflicting_source_claims) == 1
    assert conflict.unresolved_conflicts
    assert "truth_verdict" not in conflict.model_dump()
    assert result.evidence_summary.supporting_items == 1
    assert result.evidence_summary.contradicting_items == 1


def test_end_to_end_mocked_research_flow() -> None:
    search_provider = StubGroundedSearchProvider()
    result = asyncio.run(
        InvestigationResearchService(
            search_provider=search_provider,
            evidence_extractor=MockEvidenceExtractor(),
        ).research(
            _request(
                max_sub_questions=2,
                max_sources_per_question=3,
            )
        )
    )

    assert result.status == "completed"
    assert len(result.question_results) == 2
    assert search_provider.calls == [3, 3]
    assert all(
        len(question.sources) <= 3
        for question in result.question_results
    )
    assert all(
        item.provenance.source_id
        in {source.source_id for source in question.sources}
        for question in result.question_results
        for item in question.evidence_items
    )
    evidence_ids = [
        item.evidence_id
        for question in result.question_results
        for item in question.evidence_items
    ]
    assert len(evidence_ids) == len(set(evidence_ids))


def test_rate_limit_returns_partial_state_without_mock_sources() -> None:
    search_provider = StubGroundedSearchProvider(fail_on_call=2)
    result = asyncio.run(
        InvestigationResearchService(
            search_provider=search_provider,
            evidence_extractor=MockEvidenceExtractor(),
        ).research(_request(max_sub_questions=2))
    )

    assert result.status == "partial"
    assert len(result.question_results) == 1
    assert result.error is not None
    assert result.error.error_type == "rate_limit"
    assert result.error.retry_after_seconds == 12
    assert any(
        "No mock sources were substituted" in warning
        for warning in result.warnings
    )


def test_investigation_research_endpoint_response() -> None:
    search_provider = StubGroundedSearchProvider()
    evidence_extractor = MockEvidenceExtractor()

    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/investigations/research",
                json=_request().model_dump(mode="json"),
            )

    with (
        patch(
            "app.api.v1.routes.create_search_provider",
            return_value=search_provider,
        ),
        patch(
            "app.api.v1.routes.create_evidence_extractor",
            return_value=evidence_extractor,
        ),
    ):
        response = asyncio.run(make_request())

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["search_provider_used"] == "gemini_grounded"
    assert payload["evidence_provider_used"] == "mock"
    assert len(payload["question_results"]) == 1
    assert len(payload["question_results"][0]["sources"]) == 2
    assert "truth_verdict" not in payload["conflicts"][0]


def test_cost_limits_are_hard_validation_limits() -> None:
    for invalid_request in (
        {
            "query": "Research a valid bounded investigation",
            "max_sub_questions": 3,
            "max_sources_per_question": 2,
        },
        {
            "query": "Research a valid bounded investigation",
            "max_sub_questions": 2,
            "max_sources_per_question": 4,
        },
    ):
        try:
            InvestigationResearchRequest.model_validate(invalid_request)
        except ValidationError:
            pass
        else:
            raise AssertionError("Expected hard cost-limit validation")


def test_failed_endpoint_does_not_call_mock_search_provider() -> None:
    search_provider = StubGroundedSearchProvider(fail_on_call=1)
    evidence_extractor = MockEvidenceExtractor()

    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/investigations/research",
                json=_request().model_dump(mode="json"),
            )

    with (
        patch(
            "app.api.v1.routes.create_search_provider",
            return_value=search_provider,
        ),
        patch(
            "app.api.v1.routes.create_evidence_extractor",
            return_value=evidence_extractor,
        ),
        patch.object(
            MockSearchProvider,
            "search",
            new_callable=AsyncMock,
        ) as mock_search,
    ):
        response = asyncio.run(make_request())

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "failed"
    assert payload["question_results"] == []
    assert payload["error"]["error_type"] == "rate_limit"
    mock_search.assert_not_awaited()
