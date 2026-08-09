from datetime import UTC, datetime

from app.schemas.source import (
    CredibilityLevel,
    Source,
    SourceMetadata,
    SourceType,
)
from app.services.source_credibility_service import SourceCredibilityService


def test_high_quality_source_receives_explainable_high_score() -> None:
    source = Source(
        source_id="source-001",
        title="Mock peer-reviewed study",
        url="https://academic.example/study",
        author="Dr. Example",
        publisher="Example Journal",
        domain="academic.example",
        published_at=datetime(2025, 1, 10, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_type=SourceType.ACADEMIC,
        snippet="A supplied passage from the mock study.",
        metadata=SourceMetadata(
            citation_count=20,
            has_references=True,
        ),
    )

    credibility = SourceCredibilityService().assess(source)

    assert credibility.level is CredibilityLevel.HIGH
    assert credibility.score >= 80
    assert credibility.reasons
    assert "does not establish" in credibility.disclaimer


def test_sparse_unknown_source_receives_unknown_quality_score() -> None:
    source = Source(
        source_id="source-002",
        title="Mock unattributed page",
        url="http://unknown.example/page",
        domain="unknown.example",
        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_type=SourceType.UNKNOWN,
        snippet="An unattributed passage without supporting metadata.",
        metadata=SourceMetadata(has_references=False),
    )

    credibility = SourceCredibilityService().assess(source)

    assert credibility.level is CredibilityLevel.UNKNOWN
    assert credibility.score < 25
    assert credibility.warnings
    assert any("author" in warning.casefold() for warning in credibility.warnings)
