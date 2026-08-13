import asyncio
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.agents.critic_agent import CriticAgent
from app.agents.evidence_agent import EvidenceAgent
from app.agents.orchestrator import InvestigationOrchestrator
from app.agents.research_agent import ResearchAgent
from app.core.config import settings
from app.evidence.base import EvidenceProviderError
from app.evidence.mock_extractor import MockEvidenceExtractor
from app.graph.models import (
    GraphNode,
    GraphNodeType,
    GraphStats,
)
from app.main import app
from app.research.search.base import (
    SearchProvider,
    SearchProviderError,
    SearchProviderRateLimitError,
)
from app.research.search.mock_provider import MockSearchProvider
from app.rag.embeddings.mock_provider import MockEmbeddingProvider
from app.rag.vectorstore.in_memory import InMemoryVectorStore
from app.schemas.agentic import (
    AgenticInvestigationRequest,
    AgentStepStatus,
    SynthesisConfidence,
)
from app.schemas.evidence import EvidenceItem
from app.schemas.graph import (
    GraphBuildRequest,
    GraphBuildResult,
    GraphRAGContextItem,
    GraphRAGRequest,
    GraphRAGResult,
)
from app.schemas.investigation import InvestigationRequest
from app.schemas.research import SearchResult
from app.schemas.source import Source, SourceType
from app.services.rag_indexing_service import RAGIndexingService
from app.services.rag_retrieval_service import RAGRetrievalService


RETRIEVED_AT = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _search_result(
    name: str,
    source_type: SourceType,
    passage: str,
) -> SearchResult:
    return SearchResult(
        title=f"{name} source",
        url=f"https://{name}.example/report",
        snippet=passage,
        source_type=source_type,
        retrieved_at=RETRIEVED_AT,
    )


SUPPORTING = _search_result(
    "supporting",
    SourceType.ACADEMIC,
    "The supplied study reports an improvement in the measured outcome.",
)
CONTRADICTING = _search_result(
    "contradicting",
    SourceType.NEWS,
    "The supplied report documents a decline in the measured outcome.",
)
NEUTRAL = _search_result(
    "neutral",
    SourceType.REFERENCE,
    "The supplied reference defines the measurement terminology.",
)


class ScriptedSearchProvider(SearchProvider):
    def __init__(
        self,
        actions: Sequence[list[SearchResult] | Exception],
    ) -> None:
        self.actions = list(actions)
        self.calls: list[tuple[str, int]] = []

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
        del published_after, published_before
        self.calls.append((query, max_results))
        if not self.actions:
            raise AssertionError("Unexpected extra research call")
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action[:max_results]


class OneSourceFailingExtractor(MockEvidenceExtractor):
    async def extract(
        self,
        sub_question: Any,
        sources: Sequence[Source],
        *,
        investigation_query: str | None = None,
    ) -> list[EvidenceItem]:
        if sources[0].source_id == "source-002":
            raise EvidenceProviderError(
                "One source could not be extracted.",
                error_type="provider_error",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            )
        return await super().extract(
            sub_question,
            sources,
            investigation_query=investigation_query,
        )


class FabricatingExtractor(MockEvidenceExtractor):
    async def extract(
        self,
        sub_question: Any,
        sources: Sequence[Source],
        *,
        investigation_query: str | None = None,
    ) -> list[EvidenceItem]:
        items = await super().extract(
            sub_question,
            sources,
            investigation_query=investigation_query,
        )
        bad_provenance = items[0].provenance.model_copy(
            update={"source_id": "source-999"}
        )
        return [items[0].model_copy(update={"provenance": bad_provenance})]


class FakeGraphBuilderService:
    provider_name = "fake-graph-extractor"
    model_name = "fake-graph-model"

    def __init__(self) -> None:
        self.build_calls: list[GraphBuildRequest] = []

    async def build(self, request: GraphBuildRequest) -> GraphBuildResult:
        self.build_calls.append(request)
        return GraphBuildResult(
            investigation_id=request.investigation_id,
            nodes_added=0,
            edges_added=0,
            duplicates_skipped=0,
            claims_built=len(request.sub_questions),
            sources_built=len(request.sources),
            evidence_built=len(request.evidence_items),
            entities_extracted=0,
            relations_extracted=0,
            warnings=["fake graph build completed"],
            stats=GraphStats(
                store_type="in_memory",
                node_count=0,
                edge_count=0,
                investigation_count=1,
            ),
        )


class FakeGraphRAGService:
    def __init__(self) -> None:
        self.search_calls: list[GraphRAGRequest] = []

    async def search(self, request: GraphRAGRequest) -> GraphRAGResult:
        self.search_calls.append(request)
        node = GraphNode(
            node_id="graph-node-001",
            node_type=GraphNodeType.CLAIM,
            label="claim node",
        )
        return GraphRAGResult(
            query=request.query,
            vector_matches=[],
            graph_matches=[node],
            graph_paths=[],
            merged_context=[
                GraphRAGContextItem(
                    kind="claim",
                    text=request.query,
                    node_id="graph-node-001",
                    node_type="claim",
                    score=1.0,
                )
            ],
            provenance=[],
        )


def _orchestrator(
    search_provider: SearchProvider,
    extractor: MockEvidenceExtractor | None = None,
    *,
    rag_indexing_service: RAGIndexingService | None = None,
    rag_retrieval_service: RAGRetrievalService | None = None,
    graph_builder_service: FakeGraphBuilderService | None = None,
    graph_rag_service: FakeGraphRAGService | None = None,
) -> InvestigationOrchestrator:
    evidence_extractor = extractor or MockEvidenceExtractor()
    research_agent = ResearchAgent(search_provider)
    evidence_agent = EvidenceAgent(evidence_extractor)
    return InvestigationOrchestrator(
        research_agent=research_agent,
        evidence_agent=evidence_agent,
        critic_agent=CriticAgent(
            research_agent=research_agent,
            evidence_agent=evidence_agent,
            rag_indexing_service=rag_indexing_service,
            rag_retrieval_service=rag_retrieval_service,
        ),
        rag_indexing_service=rag_indexing_service,
        rag_retrieval_service=rag_retrieval_service,
        graph_builder_service=graph_builder_service,
        graph_rag_service=graph_rag_service,
    )


def _request(
    *,
    run_critic: bool = True,
    max_sub_questions: int = 1,
    max_sources_per_question: int = 2,
    max_critic_rounds: int = 1,
    use_rag: bool = False,
    use_graph_rag: bool = False,
) -> AgenticInvestigationRequest:
    return AgenticInvestigationRequest(
        query="Research long-duration storage performance",
        depth="quick",
        max_sub_questions=max_sub_questions,
        max_sources_per_question=max_sources_per_question,
        run_critic=run_critic,
        max_critic_rounds=max_critic_rounds,
        use_rag=use_rag,
        use_graph_rag=use_graph_rag,
    )


def test_full_successful_agentic_flow_with_critic() -> None:
    search = ScriptedSearchProvider(
        [[SUPPORTING, NEUTRAL], [CONTRADICTING]]
    )
    result = asyncio.run(_orchestrator(search).investigate(_request()))

    assert result.status == "completed"
    state = result.state
    assert len(state.question_results) == 1
    assert state.question_results[0].research.grounding_metadata is not None
    assert state.total_source_count == 3
    assert state.total_evidence_count == 3
    assert state.critic_result.enabled is True
    assert state.critic_result.rounds_completed == 1
    assert state.synthesis.strongest_supporting_evidence is not None
    assert state.synthesis.strongest_contradicting_evidence is not None


def test_critic_disabled_makes_no_critic_research_call() -> None:
    search = ScriptedSearchProvider([[SUPPORTING]])
    result = asyncio.run(
        _orchestrator(search).investigate(_request(run_critic=False))
    )

    assert result.state.critic_result.status == "skipped"
    assert result.state.critic_result.enabled is False
    assert len(search.calls) == 1
    critic_step = result.state.audit_trail[-2]
    assert critic_step.step_name == "critic_executed"
    assert critic_step.status is AgentStepStatus.SKIPPED


def test_agentic_use_rag_false_preserves_original_step_flow() -> None:
    search = ScriptedSearchProvider([[SUPPORTING]])
    result = asyncio.run(
        _orchestrator(search).investigate(
            _request(run_critic=False, use_rag=False)
        )
    )

    assert [step.step_name for step in result.state.audit_trail] == [
        "plan_created",
        "research_sq-01",
        "evidence_sq-01",
        "conflicts_detected",
        "critic_executed",
        "synthesis_produced",
    ]


def test_agentic_use_graph_rag_builds_graph_retrieves_context_and_notes_limit() -> None:
    search = ScriptedSearchProvider([[SUPPORTING, NEUTRAL], [CONTRADICTING]])
    embedding_provider = MockEmbeddingProvider(dimensions=32)
    vector_store = InMemoryVectorStore()
    builder = FakeGraphBuilderService()
    ragger = FakeGraphRAGService()
    result = asyncio.run(
        _orchestrator(
            search,
            rag_indexing_service=RAGIndexingService(
                embedding_provider,
                vector_store,
                chunk_size=100,
                chunk_overlap=10,
            ),
            rag_retrieval_service=RAGRetrievalService(
                embedding_provider,
                vector_store,
            ),
            graph_builder_service=builder,
            graph_rag_service=ragger,
        ).investigate(
            _request(run_critic=True, use_graph_rag=True)
        )
    )

    state = result.state
    assert state.status == "completed"
    assert len(builder.build_calls) == 1
    assert len(ragger.search_calls) == 1
    assert (
        ragger.search_calls[0].investigation_id
        == builder.build_calls[0].investigation_id
    )
    assert ragger.search_calls[0].query == builder.build_calls[0].sub_questions[0].question

    steps = [step.step_name for step in state.audit_trail]
    assert "graph_build" in steps
    assert "graph_rag_sq-01" in steps
    assert steps.index("graph_build") > steps.index("conflicts_detected")
    assert steps.index("graph_rag_sq-01") > steps.index("graph_build")
    assert steps.index("graph_rag_sq-01") < steps.index("critic_executed")

    graph_build = next(
        step for step in state.audit_trail if step.step_name == "graph_build"
    )
    assert graph_build.source_count == 2
    assert graph_build.evidence_count == 2
    assert graph_build.warnings == ["fake graph build completed"]

    assert any(
        "Graph retrieval added structural context" in limitation
        for limitation in state.synthesis.important_limitations
    )


def test_agentic_use_rag_true_indexes_retrieves_and_preserves_provenance() -> None:
    search = ScriptedSearchProvider([[SUPPORTING, NEUTRAL]])
    embedding_provider = MockEmbeddingProvider(dimensions=32)
    vector_store = InMemoryVectorStore()
    orchestrator = _orchestrator(
        search,
        rag_indexing_service=RAGIndexingService(
            embedding_provider,
            vector_store,
            chunk_size=100,
            chunk_overlap=10,
        ),
        rag_retrieval_service=RAGRetrievalService(
            embedding_provider,
            vector_store,
        ),
    )

    result = asyncio.run(
        orchestrator.investigate(
            _request(run_critic=False, use_rag=True)
        )
    )

    question_result = result.state.question_results[0]
    audit_names = [
        step.step_name for step in result.state.audit_trail
    ]
    assert "rag_index_sq-01" in audit_names
    assert "rag_retrieve_sq-01" in audit_names
    assert asyncio.run(vector_store.count()) == 2
    known_sources = {
        (source.source_id, str(source.url)): source
        for source in question_result.research.sources
    }
    assert question_result.evidence_items
    for evidence in question_result.evidence_items:
        key = (
            evidence.provenance.source_id,
            str(evidence.provenance.source_url),
        )
        assert key in known_sources
        assert evidence.provenance.relevant_passage in (
            known_sources[key].snippet or known_sources[key].title
        )
    assert all(
        item.provenance.source_id != "source-999"
        for item in question_result.evidence_items
    )


def test_agentic_rag_also_grounds_critic_research() -> None:
    search = ScriptedSearchProvider([[SUPPORTING], [CONTRADICTING]])
    embedding_provider = MockEmbeddingProvider(dimensions=32)
    vector_store = InMemoryVectorStore()
    orchestrator = _orchestrator(
        search,
        rag_indexing_service=RAGIndexingService(
            embedding_provider,
            vector_store,
            chunk_size=100,
            chunk_overlap=10,
        ),
        rag_retrieval_service=RAGRetrievalService(
            embedding_provider,
            vector_store,
        ),
    )

    result = asyncio.run(
        orchestrator.investigate(
            _request(
                run_critic=True,
                max_sources_per_question=1,
                use_rag=True,
            )
        )
    )

    critic = result.state.critic_result
    assert critic.new_evidence_items
    known_critic_sources = {
        (source.source_id, str(source.url)): source
        for source in critic.new_sources
    }
    for evidence in critic.new_evidence_items:
        key = (
            evidence.provenance.source_id,
            str(evidence.provenance.source_url),
        )
        assert key in known_critic_sources
        assert evidence.provenance.relevant_passage in (
            known_critic_sources[key].snippet
            or known_critic_sources[key].title
        )


def test_critic_finds_genuine_contradicting_evidence() -> None:
    search = ScriptedSearchProvider([[SUPPORTING], [CONTRADICTING]])
    result = asyncio.run(_orchestrator(search).investigate(_request()))

    critic = result.state.critic_result
    assert critic.opposing_evidence_ids
    assert critic.new_evidence_items[0].stance.value == "contradicts"
    assert "source-grounded" in critic.finding_summary


def test_critic_finds_no_new_evidence_without_misclassifying_absence() -> None:
    search = ScriptedSearchProvider([[SUPPORTING], [SUPPORTING]])
    result = asyncio.run(_orchestrator(search).investigate(_request()))

    critic = result.state.critic_result
    assert critic.new_sources == []
    assert critic.new_evidence_items == []
    assert critic.opposing_evidence_ids == []
    assert "evidence gap" in critic.finding_summary
    assert "not contradictory" in critic.finding_summary


def test_one_sub_question_failure_returns_partial_and_continues() -> None:
    failure = SearchProviderError(
        "One research question failed.",
        error_type="provider_error",
        provider="gemini_grounded",
        model="mocked-grounded-model",
        retryable=False,
    )
    search = ScriptedSearchProvider([failure, [SUPPORTING]])
    result = asyncio.run(
        _orchestrator(search).investigate(
            _request(run_critic=False, max_sub_questions=2)
        )
    )

    assert result.status == "partial"
    assert len(result.state.question_results) == 1
    assert result.state.errors[0].error_type == "provider_error"
    assert result.state.audit_trail[1].status is AgentStepStatus.FAILED
    assert result.state.audit_trail[2].step_name == "research_sq-02"


def test_rate_limit_is_propagated_and_stops_additional_search() -> None:
    rate_limit = SearchProviderRateLimitError(
        provider="gemini_grounded",
        model="mocked-grounded-model",
        retry_after_seconds=9,
    )
    search = ScriptedSearchProvider([rate_limit, [CONTRADICTING]])
    result = asyncio.run(
        _orchestrator(search).investigate(
            _request(max_sub_questions=2, max_critic_rounds=2)
        )
    )

    assert result.status == "failed"
    assert len(search.calls) == 1
    assert result.state.errors[0].error_type == "rate_limit"
    assert result.state.errors[0].retry_after_seconds == 9
    assert result.state.critic_result.status == "partial"
    assert "No mock sources were substituted" in (
        result.state.critic_result.finding_summary
    )


def test_one_source_evidence_failure_preserves_other_evidence() -> None:
    search = ScriptedSearchProvider([[SUPPORTING, NEUTRAL]])
    result = asyncio.run(
        _orchestrator(search, OneSourceFailingExtractor()).investigate(
            _request(run_critic=False)
        )
    )

    question = result.state.question_results[0]
    assert result.status == "partial"
    assert question.status == "partial"
    assert len(question.evidence_items) == 1
    assert question.evidence_items[0].provenance.source_id == "source-001"
    assert question.errors[0].error_type == "provider_error"


def test_hard_agent_iteration_limits_are_enforced() -> None:
    invalid_payloads = [
        {"max_sub_questions": 3},
        {"max_sources_per_question": 4},
        {"max_critic_rounds": 3},
    ]
    for limits in invalid_payloads:
        with pytest.raises(ValidationError):
            AgenticInvestigationRequest.model_validate(
                {
                    "query": "Research a bounded agent workflow",
                    **limits,
                }
            )

    research = ResearchAgent(ScriptedSearchProvider([]))
    evidence = EvidenceAgent(MockEvidenceExtractor())
    critic = CriticAgent(
        research_agent=research,
        evidence_agent=evidence,
    )
    with pytest.raises(ValueError, match="between 1 and 2"):
        asyncio.run(
            critic.run(
                original_query="Research a bounded critic",
                current_evidence=[],
                known_sources=[],
                investigation_context="test",
                max_rounds=3,
            )
        )


def test_audit_trail_ordering_and_public_metadata_only() -> None:
    search = ScriptedSearchProvider([[SUPPORTING], [CONTRADICTING]])
    result = asyncio.run(_orchestrator(search).investigate(_request()))

    audit = result.state.audit_trail
    assert [step.step_name for step in audit] == [
        "plan_created",
        "research_sq-01",
        "evidence_sq-01",
        "conflicts_detected",
        "critic_executed",
        "synthesis_produced",
    ]
    assert [step.step_id for step in audit] == [
        f"step-{index:03d}" for index in range(1, 7)
    ]
    assert all(step.completed_at >= step.started_at for step in audit)
    serialized = result.model_dump(mode="json")
    serialized_text = str(serialized).casefold()
    assert "chain_of_thought" not in serialized_text
    assert "private_reasoning" not in serialized_text


def test_evidence_agent_rejects_fabricated_source_provenance() -> None:
    search = ScriptedSearchProvider([[SUPPORTING]])
    result = asyncio.run(
        _orchestrator(search, FabricatingExtractor()).investigate(
            _request(run_critic=False)
        )
    )

    assert result.status == "partial"
    assert result.state.question_results[0].evidence_items == []
    assert result.state.errors[0].error_type == "grounding_validation"
    assert result.state.total_evidence_count == 0


def test_confidence_is_about_evidence_picture_and_no_truth_verdict() -> None:
    search = ScriptedSearchProvider([[SUPPORTING], [CONTRADICTING]])
    result = asyncio.run(_orchestrator(search).investigate(_request()))

    synthesis = result.state.synthesis
    assert synthesis.confidence_level in set(SynthesisConfidence)
    assert "evidence picture" in synthesis.confidence_rationale
    assert "not a probability" in synthesis.confidence_rationale
    serialized = result.model_dump(mode="json")

    def keys(value: Any) -> list[str]:
        if isinstance(value, dict):
            return [
                *(str(key) for key in value),
                *(nested for item in value.values() for nested in keys(item)),
            ]
        if isinstance(value, list):
            return [nested for item in value for nested in keys(item)]
        return []

    assert "truth_verdict" not in keys(serialized)
    assert "verdict" not in keys(serialized)


def test_orchestrator_accepts_base_investigation_request() -> None:
    search = ScriptedSearchProvider(
        [[SUPPORTING], [NEUTRAL], [CONTRADICTING]]
    )
    result = asyncio.run(
        _orchestrator(search).investigate(
            InvestigationRequest(
                query="Research base investigation request support",
                depth="quick",
            )
        )
    )
    assert result.state.plan.query == (
        "Research base investigation request support"
    )


def test_agentic_api_endpoint_response() -> None:
    search_provider = ScriptedSearchProvider(
        [[SUPPORTING], [CONTRADICTING]]
    )
    evidence_extractor = MockEvidenceExtractor()

    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/investigations/agentic",
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
    assert payload["status"] == "completed"
    assert payload["state"]["critic_result"]["enabled"] is True
    assert payload["state"]["audit_trail"][-1]["step_name"] == (
        "synthesis_produced"
    )
    assert "truth_verdict" not in payload["state"]["synthesis"]
    mock_search.assert_not_awaited()


def test_agentic_api_use_rag_true_uses_offline_rag_flow() -> None:
    search_provider = ScriptedSearchProvider([[SUPPORTING]])
    evidence_extractor = MockEvidenceExtractor()
    embedding_provider = MockEmbeddingProvider(dimensions=32)
    vector_store = InMemoryVectorStore()

    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/investigations/agentic",
                json=_request(
                    run_critic=False,
                    max_sources_per_question=1,
                    use_rag=True,
                ).model_dump(mode="json"),
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
        patch(
            "app.api.v1.routes.create_embedding_provider",
            return_value=embedding_provider,
        ),
        patch(
            "app.api.v1.routes.get_vector_store",
            return_value=vector_store,
        ),
    ):
        response = asyncio.run(make_request())

    assert response.status_code == 200
    payload = response.json()
    audit_names = [
        step["step_name"]
        for step in payload["state"]["audit_trail"]
    ]
    assert "rag_index_sq-01" in audit_names
    assert "rag_retrieve_sq-01" in audit_names
    evidence = payload["state"]["question_results"][0]["evidence_items"][0]
    assert evidence["provenance"]["source_id"] == "source-001"
    assert evidence["provenance"]["source_url"] == (
        "https://supporting.example/report"
    )


def test_agentic_api_defers_provider_choice_to_configuration() -> None:
    recorded: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def spy_factory(*args: Any, **kwargs: Any) -> SearchProvider:
        recorded.append((args, kwargs))
        return ScriptedSearchProvider([[SUPPORTING]])

    evidence_extractor = MockEvidenceExtractor()

    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/investigations/agentic",
                json=_request(run_critic=False).model_dump(mode="json"),
            )

    with (
        patch(
            "app.api.v1.routes.create_search_provider",
            side_effect=spy_factory,
        ),
        patch(
            "app.api.v1.routes.create_evidence_extractor",
            return_value=evidence_extractor,
        ),
    ):
        response = asyncio.run(make_request())

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert recorded, "create_search_provider was never called by the route"
    args, kwargs = recorded[0]
    assert args == ()
    assert "provider_name" not in kwargs


def test_agentic_api_runs_offline_with_mock_config_and_never_builds_gemini() -> None:
    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/investigations/agentic",
                json=_request(run_critic=False).model_dump(mode="json"),
            )

    with (
        patch(
            "app.research.search.factory.GeminiGroundedSearchProvider",
        ) as gemini_cls,
        patch(
            "app.research.search.factory.settings",
            replace(settings, SEARCH_PROVIDER="mock"),
        ),
    ):
        response = asyncio.run(make_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert (
        payload["state"]["question_results"][0]["research"]["provider_used"]
        == "mock"
    )
    gemini_cls.assert_not_called()


def test_agentic_api_surfaces_configured_gemini_rate_limit_without_mock_fallback() -> None:
    rate_limit = SearchProviderRateLimitError(
        provider="gemini_grounded",
        model="mocked-grounded-model",
        retry_after_seconds=9,
    )
    search_provider = ScriptedSearchProvider([rate_limit])
    evidence_extractor = MockEvidenceExtractor()

    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/investigations/agentic",
                json=_request(
                    max_sub_questions=2,
                    max_critic_rounds=2,
                ).model_dump(mode="json"),
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

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["state"]["errors"][0]["error_type"] == "rate_limit"
    assert payload["state"]["errors"][0]["retry_after_seconds"] == 9
    assert len(search_provider.calls) == 1
    assert "No mock sources were substituted" in (
        payload["state"]["critic_result"]["finding_summary"]
    )
