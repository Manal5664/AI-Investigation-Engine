import asyncio

from app.evidence.mock_extractor import MockEvidenceExtractor
from app.research.search.mock_provider import MockSearchProvider
from app.schemas.evidence import (
    EvidenceStance,
    EvidenceStrength,
)
from app.schemas.investigation import (
    InvestigationDepth,
    InvestigationRequest,
)
from app.services.evidence_summary_service import EvidenceSummaryService
from app.services.investigation_service import InvestigationPlanner
from app.services.research_service import ResearchService
from app.services.source_credibility_service import SourceCredibilityService


planner = InvestigationPlanner()


def _build_research_service() -> ResearchService:
    return ResearchService(
        search_provider=MockSearchProvider(),
        evidence_extractor=MockEvidenceExtractor(),
    )


def test_source_normalization_preserves_search_metadata() -> None:
    search_results = asyncio.run(
        MockSearchProvider().search("A valid research query", 2)
    )

    sources = ResearchService.normalize_sources(search_results)

    assert [source.source_id for source in sources] == [
        "source-001",
        "source-002",
    ]
    assert sources[0].domain == "academic.example"
    assert sources[0].snippet == search_results[0].snippet
    assert sources[0].metadata == search_results[0].metadata


def test_mock_extractor_preserves_provenance_and_classifies_stance() -> None:
    search_results = asyncio.run(
        MockSearchProvider().search("A valid research query", 8)
    )
    normalized_sources = ResearchService.normalize_sources(search_results)
    credibility_service = SourceCredibilityService()
    assessed_sources = [
        source.model_copy(
            update={"credibility": credibility_service.assess(source)}
        )
        for source in normalized_sources
    ]
    plan = planner.plan(
        InvestigationRequest(query="Research renewable energy storage")
    )

    evidence_items = asyncio.run(
        MockEvidenceExtractor().extract(
            plan.sub_questions[0],
            assessed_sources,
        )
    )

    known_sources = {
        (source.source_id, str(source.url), source.snippet)
        for source in assessed_sources
    }
    assert len(evidence_items) == len(assessed_sources)
    assert {
        item.stance
        for item in evidence_items
    } >= {
        EvidenceStance.SUPPORTS,
        EvidenceStance.CONTRADICTS,
        EvidenceStance.NEUTRAL,
        EvidenceStance.INSUFFICIENT,
    }
    assert any(
        item.strength is EvidenceStrength.STRONG
        for item in evidence_items
    )
    assert any(
        item.stance is EvidenceStance.INSUFFICIENT
        and item.strength is EvidenceStrength.UNKNOWN
        for item in evidence_items
    )
    for item in evidence_items:
        assert (
            item.provenance.source_id,
            str(item.provenance.source_url),
            item.provenance.relevant_passage,
        ) in known_sources
        assert item.provenance.content_hash is not None
        assert len(item.provenance.content_hash) == 64


def test_extractor_never_references_unknown_sources() -> None:
    search_results = asyncio.run(
        MockSearchProvider().search("A valid research query", 2)
    )
    supplied_sources = ResearchService.normalize_sources(search_results)
    plan = planner.plan(
        InvestigationRequest(query="Research renewable energy storage")
    )

    evidence_items = asyncio.run(
        MockEvidenceExtractor().extract(
            plan.sub_questions[0],
            supplied_sources,
        )
    )

    supplied_ids = {source.source_id for source in supplied_sources}
    assert {
        item.provenance.source_id
        for item in evidence_items
    } <= supplied_ids


def test_research_service_orchestrates_pipeline() -> None:
    plan = planner.plan(
        InvestigationRequest(query="Research renewable energy storage")
    )

    result = asyncio.run(
        _build_research_service().research(plan, max_results=5)
    )

    assert result.investigation_query == plan.query
    assert result.sub_question == plan.sub_questions[0]
    assert len(result.sources) == 5
    assert len(result.evidence_items) == 5
    assert result.counts_by_stance.supports == 2
    assert result.counts_by_stance.contradicts == 1
    assert result.counts_by_stance.neutral == 2
    assert result.counts_by_stance.insufficient == 0
    assert all(source.credibility is not None for source in result.sources)
    assert "do not establish" in result.warnings[0]


def test_research_pipeline_supports_all_investigation_depths() -> None:
    service = _build_research_service()

    for depth in InvestigationDepth:
        plan = planner.plan(
            InvestigationRequest(
                query="Research renewable energy storage",
                depth=depth,
            )
        )
        result = asyncio.run(service.research(plan, max_results=3))

        assert result.depth is depth
        assert result.sub_question.id == plan.sub_questions[0].id
        assert len(result.sources) == 3


def test_evidence_summary_reports_conflicts_without_truth_verdict() -> None:
    plan = planner.plan(
        InvestigationRequest(query="Research renewable energy storage")
    )
    research_result = asyncio.run(
        _build_research_service().research(plan, max_results=5)
    )

    summary = EvidenceSummaryService().summarize(research_result)

    assert summary.supporting_items == 2
    assert summary.contradicting_items == 1
    assert summary.neutral_items == 2
    assert summary.insufficient_items == 0
    assert summary.strongest_supporting_evidence is not None
    assert summary.strongest_contradicting_evidence is not None
    assert summary.unresolved_conflicts
    assert all(
        "truth" not in conflict.casefold()
        for conflict in summary.unresolved_conflicts
    )
