import asyncio
import hashlib
from collections.abc import Sequence
from typing import ClassVar

from app.evidence.base import EvidenceExtractor
from app.schemas.evidence import (
    EvidenceItem,
    EvidenceProvenance,
    EvidenceStance,
    EvidenceStrength,
)
from app.schemas.investigation import InvestigationSubQuestion
from app.schemas.source import CredibilityLevel, Source, SourceType


class MockEvidenceExtractor(EvidenceExtractor):
    _STANCE_BY_SOURCE_TYPE: ClassVar[dict[SourceType, EvidenceStance]] = {
        SourceType.ACADEMIC: EvidenceStance.SUPPORTS,
        SourceType.GOVERNMENT: EvidenceStance.NEUTRAL,
        SourceType.OFFICIAL_ORGANIZATION: EvidenceStance.SUPPORTS,
        SourceType.NEWS: EvidenceStance.CONTRADICTS,
        SourceType.REFERENCE: EvidenceStance.NEUTRAL,
        SourceType.BLOG: EvidenceStance.INSUFFICIENT,
        SourceType.SOCIAL_MEDIA: EvidenceStance.INSUFFICIENT,
        SourceType.UNKNOWN: EvidenceStance.INSUFFICIENT,
    }
    _STRENGTH_BY_CREDIBILITY: ClassVar[
        dict[CredibilityLevel, EvidenceStrength]
    ] = {
        CredibilityLevel.HIGH: EvidenceStrength.STRONG,
        CredibilityLevel.MODERATE: EvidenceStrength.MODERATE,
        CredibilityLevel.LOW: EvidenceStrength.WEAK,
        CredibilityLevel.UNKNOWN: EvidenceStrength.UNKNOWN,
    }

    async def extract(
        self,
        sub_question: InvestigationSubQuestion,
        sources: Sequence[Source],
    ) -> list[EvidenceItem]:
        await asyncio.sleep(0)
        evidence_items = [
            self._extract_from_source(index, sub_question, source)
            for index, source in enumerate(sources, start=1)
        ]
        self._assert_known_provenance(evidence_items, sources)
        return evidence_items

    def _extract_from_source(
        self,
        index: int,
        sub_question: InvestigationSubQuestion,
        source: Source,
    ) -> EvidenceItem:
        passage = source.snippet or source.title
        stance = self._STANCE_BY_SOURCE_TYPE[source.source_type]
        credibility_level = (
            source.credibility.level
            if source.credibility is not None
            else CredibilityLevel.UNKNOWN
        )
        strength = (
            EvidenceStrength.UNKNOWN
            if stance is EvidenceStance.INSUFFICIENT
            else self._STRENGTH_BY_CREDIBILITY[credibility_level]
        )

        return EvidenceItem(
            evidence_id=f"evidence-{index:03d}",
            sub_question_id=sub_question.id,
            summary=(
                f"The supplied passage from '{source.title}' was classified "
                f"as {stance.value} for the selected sub-question."
            ),
            stance=stance,
            strength=strength,
            provenance=EvidenceProvenance(
                source_id=source.source_id,
                source_url=source.url,
                relevant_passage=passage,
                retrieved_at=source.retrieved_at,
                extraction_method="mock_deterministic_snippet",
                content_hash=hashlib.sha256(passage.encode("utf-8")).hexdigest(),
                location=(
                    "search_result.snippet"
                    if source.snippet is not None
                    else "source.title"
                ),
            ),
        )

    @staticmethod
    def _assert_known_provenance(
        evidence_items: Sequence[EvidenceItem],
        sources: Sequence[Source],
    ) -> None:
        known_sources = {
            (source.source_id, str(source.url))
            for source in sources
        }
        for item in evidence_items:
            provenance_key = (
                item.provenance.source_id,
                str(item.provenance.source_url),
            )
            if provenance_key not in known_sources:
                raise ValueError(
                    "Evidence provenance references an unknown source"
                )
