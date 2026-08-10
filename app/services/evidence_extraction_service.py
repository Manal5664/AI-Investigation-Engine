from collections import Counter

from app.evidence.base import EvidenceExtractor
from app.schemas.evidence import (
    EvidenceExtractionRequest,
    EvidenceExtractionResponse,
    EvidenceStance,
    EvidenceStanceCounts,
)
from app.schemas.investigation import InvestigationSubQuestion


class EvidenceExtractionService:
    def __init__(self, extractor: EvidenceExtractor) -> None:
        self._extractor = extractor

    async def extract(
        self,
        request: EvidenceExtractionRequest,
    ) -> EvidenceExtractionResponse:
        sub_question = InvestigationSubQuestion(
            id="sq-00",
            question=request.sub_question.strip(),
            purpose="User-supplied evidence extraction sub-question.",
            priority=1,
        )
        evidence_items = await self._extractor.extract(
            sub_question,
            request.sources,
            investigation_query=request.query,
        )
        counts = Counter(item.stance for item in evidence_items)
        warnings = [
            "Evidence stance and strength are source-bound classifications, "
            "not a truth verdict."
        ]
        insufficient_count = counts[EvidenceStance.INSUFFICIENT]
        if insufficient_count:
            warnings.append(
                f"{insufficient_count} supplied source(s) contained "
                "insufficient material for the requested classification."
            )

        return EvidenceExtractionResponse(
            provider_used=self._extractor.provider_name,
            model_used=self._extractor.model_name,
            evidence_items=evidence_items,
            stance_counts=EvidenceStanceCounts(
                supports=counts[EvidenceStance.SUPPORTS],
                contradicts=counts[EvidenceStance.CONTRADICTS],
                neutral=counts[EvidenceStance.NEUTRAL],
                insufficient=insufficient_count,
            ),
            warnings=warnings,
        )
