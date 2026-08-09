from typing import ClassVar

from app.schemas.source import (
    CredibilityLevel,
    Source,
    SourceCredibility,
    SourceType,
)


class SourceCredibilityService:
    _SOURCE_TYPE_SCORES: ClassVar[dict[SourceType, int]] = {
        SourceType.ACADEMIC: 35,
        SourceType.GOVERNMENT: 35,
        SourceType.OFFICIAL_ORGANIZATION: 30,
        SourceType.REFERENCE: 25,
        SourceType.NEWS: 20,
        SourceType.BLOG: 10,
        SourceType.SOCIAL_MEDIA: 0,
        SourceType.UNKNOWN: 0,
    }

    def assess(self, source: Source) -> SourceCredibility:
        score = self._SOURCE_TYPE_SCORES[source.source_type]
        reasons = [
            (
                f"Source type '{source.source_type.value}' contributes "
                f"{score} points."
            )
        ]
        warnings: list[str] = []

        if source.author:
            score += 10
            reasons.append("An author or responsible team is identified.")
        else:
            warnings.append("No author or responsible team is identified.")

        if source.published_at is not None:
            score += 10
            reasons.append("A publication date is available.")
        else:
            warnings.append("No publication date is available.")

        if source.url.scheme == "https":
            score += 10
            reasons.append("The source URL uses HTTPS.")
        else:
            warnings.append("The source URL does not use HTTPS.")

        if source.domain:
            score += 8
            reasons.append("A source domain is available.")
        else:
            warnings.append("No source domain is available.")

        if source.publisher:
            score += 7
            reasons.append("A publisher or organization is identified.")
        else:
            warnings.append("No publisher or organization is identified.")

        if source.metadata.has_references is True:
            score += 10
            reasons.append("The source reports references or citations.")
        elif source.metadata.has_references is False:
            warnings.append("The source reports no references or citations.")
        else:
            warnings.append("Reference metadata is unavailable.")

        if (
            source.metadata.citation_count is not None
            and source.metadata.citation_count > 0
        ):
            score += 5
            reasons.append("Citation-count metadata is available.")

        score = min(score, 100)
        return SourceCredibility(
            level=self._level_for_score(score),
            score=score,
            reasons=reasons,
            warnings=warnings,
        )

    @staticmethod
    def _level_for_score(score: int) -> CredibilityLevel:
        if score >= 80:
            return CredibilityLevel.HIGH
        if score >= 60:
            return CredibilityLevel.MODERATE
        if score >= 25:
            return CredibilityLevel.LOW
        return CredibilityLevel.UNKNOWN
