import asyncio
from typing import Any

import httpx

from app.main import app


def _post(path: str, body: dict[str, Any]) -> httpx.Response:
    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(path, json=body)

    return asyncio.run(make_request())


def test_mock_research_api_endpoint() -> None:
    response = _post(
        "/api/v1/research/mock",
        {
            "investigation_query": "Research renewable energy storage",
            "max_results": 5,
            "depth": "standard",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["investigation_query"] == (
        "Research renewable energy storage"
    )
    assert len(payload["sources"]) == 5
    assert len(payload["evidence_items"]) == 5
    assert payload["counts_by_stance"] == {
        "supports": 2,
        "contradicts": 1,
        "neutral": 2,
        "insufficient": 0,
    }
    source_ids = {source["source_id"] for source in payload["sources"]}
    assert {
        item["provenance"]["source_id"]
        for item in payload["evidence_items"]
    } <= source_ids


def test_mock_research_api_accepts_custom_sub_question() -> None:
    response = _post(
        "/api/v1/research/mock",
        {
            "investigation_query": "Research renewable energy storage",
            "sub_question": (
                "Which primary sources describe long-duration storage?"
            ),
            "max_results": 3,
            "depth": "deep",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["depth"] == "deep"
    assert payload["sub_question"]["id"] == "sq-00"
    assert payload["sub_question"]["question"] == (
        "Which primary sources describe long-duration storage?"
    )


def test_evidence_summary_api_endpoint() -> None:
    research_response = _post(
        "/api/v1/research/mock",
        {
            "investigation_query": "Research renewable energy storage",
            "max_results": 5,
        },
    )
    assert research_response.status_code == 200

    summary_response = _post(
        "/api/v1/evidence/summary",
        research_response.json(),
    )
    payload = summary_response.json()

    assert summary_response.status_code == 200
    assert payload["supporting_items"] == 2
    assert payload["contradicting_items"] == 1
    assert payload["neutral_items"] == 2
    assert payload["insufficient_items"] == 0
    assert payload["strongest_supporting_evidence"] is not None
    assert payload["strongest_contradicting_evidence"] is not None
    assert payload["unresolved_conflicts"]
    assert "verdict" not in payload


def test_research_api_rejects_malformed_input() -> None:
    empty_query_response = _post(
        "/api/v1/research/mock",
        {
            "investigation_query": "   ",
            "max_results": 5,
        },
    )
    invalid_count_response = _post(
        "/api/v1/research/mock",
        {
            "investigation_query": "A valid investigation query",
            "max_results": 0,
        },
    )

    assert empty_query_response.status_code == 422
    assert invalid_count_response.status_code == 422


def test_evidence_summary_rejects_malformed_source_url() -> None:
    research_response = _post(
        "/api/v1/research/mock",
        {
            "investigation_query": "Research renewable energy storage",
            "max_results": 2,
        },
    )
    payload = research_response.json()
    payload["sources"][0]["url"] = "not-a-url"

    summary_response = _post("/api/v1/evidence/summary", payload)

    assert summary_response.status_code == 422
