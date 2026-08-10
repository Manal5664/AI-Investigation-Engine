import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import ApplicationConfigurationError
from app.evidence.base import EvidenceProviderError
from app.evidence.factory import create_evidence_extractor
from app.evidence.gemini_extractor import GeminiEvidenceExtractor
from app.main import app
from app.schemas.evidence import EvidenceStance, EvidenceStrength
from app.schemas.investigation import InvestigationSubQuestion
from app.schemas.source import Source, SourceType


RETRIEVED_AT = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _source(
    index: int,
    passage: str,
) -> Source:
    return Source(
        source_id=f"source-{index:03d}",
        title=f"Source {index}",
        url=f"https://source{index}.example/report",
        domain=f"source{index}.example",
        retrieved_at=RETRIEVED_AT,
        source_type=SourceType.ACADEMIC,
        snippet=passage,
    )


def _sub_question() -> InvestigationSubQuestion:
    return InvestigationSubQuestion(
        id="sq-01",
        question="Does the supplied evidence support the storage claim?",
        purpose="Classify supplied evidence.",
        priority=1,
    )


def _candidate(
    source: Source,
    stance: str,
    strength: str,
) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "source_url": str(source.url),
        "relevant_passage": source.snippet,
        "stance": stance,
        "strength": strength,
        "rationale": f"The supplied passage is {stance} evidence.",
    }


def _provider(
    payload: Any = None,
    *,
    side_effect: Exception | None = None,
) -> tuple[GeminiEvidenceExtractor, AsyncMock]:
    response = SimpleNamespace(text=json.dumps(payload))
    generate_content = AsyncMock(
        side_effect=side_effect,
        return_value=response,
    )
    client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
    )
    return (
        GeminiEvidenceExtractor(
            model_name="gemini-evidence-test",
            api_key="test-api-key",
            client=client,
        ),
        generate_content,
    )


def test_gemini_evidence_success_covers_all_stances() -> None:
    sources = [
        _source(1, "Storage duration increased in the reported trial."),
        _source(2, "The reported trial found no duration improvement."),
        _source(3, "The report defines long-duration storage terminology."),
        _source(4, "The snippet contains no outcome measurements."),
    ]
    payload = {
        "evidence_items": [
            _candidate(sources[0], "supports", "strong"),
            _candidate(sources[1], "contradicts", "moderate"),
            _candidate(sources[2], "neutral", "weak"),
            _candidate(sources[3], "insufficient", "unknown"),
        ]
    }
    provider, generate_content = _provider(payload)

    items = asyncio.run(
        provider.extract(
            _sub_question(),
            sources,
            investigation_query="Long-duration storage improves duration",
        )
    )

    assert [item.stance for item in items] == [
        EvidenceStance.SUPPORTS,
        EvidenceStance.CONTRADICTS,
        EvidenceStance.NEUTRAL,
        EvidenceStance.INSUFFICIENT,
    ]
    assert [item.strength for item in items] == [
        EvidenceStrength.STRONG,
        EvidenceStrength.MODERATE,
        EvidenceStrength.WEAK,
        EvidenceStrength.UNKNOWN,
    ]
    assert generate_content.await_count == 1
    call = generate_content.await_args
    assert call is not None
    assert call.kwargs["model"] == "gemini-evidence-test"
    assert "Absence of supporting evidence is not contradiction" in (
        call.kwargs["contents"]
    )
    assert "structured JSON only" in call.kwargs["contents"]


def test_gemini_evidence_preserves_verified_provenance() -> None:
    source = _source(1, "A verbatim grounded passage from the source.")
    provider, _ = _provider(
        {"evidence_items": [_candidate(source, "supports", "strong")]}
    )

    item = asyncio.run(
        provider.extract(
            _sub_question(),
            [source],
            investigation_query="A grounded claim",
        )
    )[0]

    assert item.provenance.source_id == source.source_id
    assert item.provenance.source_url == source.url
    assert item.provenance.relevant_passage == source.snippet
    assert item.provenance.retrieved_at == RETRIEVED_AT
    assert item.provenance.model_used == "gemini-evidence-test"
    assert item.provenance.extraction_method == (
        "gemini_structured_source_extraction"
    )
    assert item.provenance.location == "source.snippet"
    assert item.provenance.content_hash is not None
    assert item.rationale


def test_gemini_evidence_rejects_unknown_source() -> None:
    source = _source(1, "Known supplied passage.")
    unknown = _source(2, "Unknown passage.")
    provider, _ = _provider(
        {"evidence_items": [_candidate(unknown, "supports", "strong")]}
    )

    with pytest.raises(
        EvidenceProviderError,
        match="unknown source ID",
    ) as captured:
        asyncio.run(provider.extract(_sub_question(), [source]))

    assert captured.value.error_type == "grounding_validation"
    assert captured.value.retryable is False


def test_gemini_evidence_rejects_fabricated_passage() -> None:
    source = _source(1, "Only this supplied passage is allowed.")
    candidate = _candidate(source, "supports", "strong")
    candidate["relevant_passage"] = "This passage was fabricated."
    provider, _ = _provider({"evidence_items": [candidate]})

    with pytest.raises(
        EvidenceProviderError,
        match="not present verbatim",
    ):
        asyncio.run(provider.extract(_sub_question(), [source]))


def test_gemini_evidence_rejects_changed_source_url() -> None:
    source = _source(1, "Only the supplied URL is allowed.")
    candidate = _candidate(source, "neutral", "weak")
    candidate["source_url"] = "https://fabricated.example/report"
    provider, _ = _provider({"evidence_items": [candidate]})

    with pytest.raises(
        EvidenceProviderError,
        match="changed a supplied source URL",
    ):
        asyncio.run(provider.extract(_sub_question(), [source]))


@pytest.mark.parametrize("response_text", ["not-json", "{}"])
def test_gemini_evidence_rejects_malformed_output(
    response_text: str,
) -> None:
    source = _source(1, "Supplied material.")
    provider, generate_content = _provider({})
    generate_content.return_value = SimpleNamespace(text=response_text)

    with pytest.raises(EvidenceProviderError) as captured:
        asyncio.run(provider.extract(_sub_question(), [source]))

    assert captured.value.error_type == "malformed_output"


@pytest.mark.parametrize(
    ("provider_exception", "expected_type", "retryable"),
    [
        (TimeoutError(), "timeout", True),
        (RuntimeError("network unavailable"), "provider_error", False),
    ],
)
def test_gemini_evidence_wraps_timeout_and_provider_errors(
    provider_exception: Exception,
    expected_type: str,
    retryable: bool,
) -> None:
    source = _source(1, "Supplied material.")
    provider, _ = _provider(side_effect=provider_exception)

    with pytest.raises(EvidenceProviderError) as captured:
        asyncio.run(provider.extract(_sub_question(), [source]))

    assert captured.value.error_type == expected_type
    assert captured.value.retryable is retryable
    assert captured.value.provider == "gemini"
    assert captured.value.model == "gemini-evidence-test"


def test_gemini_evidence_requires_api_key() -> None:
    with pytest.raises(
        ApplicationConfigurationError,
        match="GEMINI_API_KEY is required",
    ):
        GeminiEvidenceExtractor(
            model_name="gemini-evidence-test",
            api_key=None,
        )


def test_evidence_factory_selects_configured_gemini() -> None:
    config = replace(
        settings,
        EVIDENCE_PROVIDER="gemini",
        EVIDENCE_MODEL="configured-evidence-model",
        GEMINI_API_KEY="test-api-key",
    )
    sentinel = object()
    with patch(
        "app.evidence.factory.GeminiEvidenceExtractor",
        return_value=sentinel,
    ) as extractor_class:
        extractor = create_evidence_extractor(config=config)

    assert extractor is sentinel
    extractor_class.assert_called_once_with(
        model_name="configured-evidence-model",
        api_key="test-api-key",
        timeout_seconds=config.LLM_TIMEOUT_SECONDS,
    )


def test_evidence_extraction_endpoint_response() -> None:
    source = _source(1, "Endpoint source-grounded passage.")
    provider, _ = _provider(
        {"evidence_items": [_candidate(source, "supports", "strong")]}
    )

    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/evidence/extract",
                json={
                    "query": "A sufficiently detailed investigation query",
                    "sub_question": "Does the supplied source support it?",
                    "sources": [source.model_dump(mode="json")],
                },
            )

    with patch(
        "app.api.v1.research_routes.create_evidence_extractor",
        return_value=provider,
    ):
        response = asyncio.run(make_request())

    payload = response.json()
    assert response.status_code == 200
    assert payload["provider_used"] == "gemini"
    assert payload["model_used"] == "gemini-evidence-test"
    assert payload["stance_counts"]["supports"] == 1
    assert payload["evidence_items"][0]["provenance"]["source_id"] == (
        "source-001"
    )
