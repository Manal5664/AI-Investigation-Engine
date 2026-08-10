from typing import ClassVar

from app.schemas.evidence import (
    EvidenceItem,
    EvidenceStance,
    EvidenceStrength,
    EvidenceSummary,
)
from app.schemas.research import ResearchResult


class EvidenceSummaryService:
    _STRENGTH_RANK: ClassVar[dict[EvidenceStrength, int]] = {
        EvidenceStrength.UNKNOWN: 0,
        EvidenceStrength.WEAK: 1,
        EvidenceStrength.MODERATE: 2,
        EvidenceStrength.STRONG: 3,
    }

    def summarize(self, research_result: ResearchResult) -> EvidenceSummary:
        return self.summarize_items(research_result.evidence_items)

    def summarize_items(
        self,
        evidence_items: list[EvidenceItem],
    ) -> EvidenceSummary:
        supporting = self._items_with_stance(
            evidence_items,
            EvidenceStance.SUPPORTS,
        )
        contradicting = self._items_with_stance(
            evidence_items,
            EvidenceStance.CONTRADICTS,
        )
        neutral = self._items_with_stance(
            evidence_items,
            EvidenceStance.NEUTRAL,
        )
        insufficient = self._items_with_stance(
            evidence_items,
            EvidenceStance.INSUFFICIENT,
        )

        unresolved_conflicts: list[str] = []
        if supporting and contradicting:
            unresolved_conflicts.append(
                "Supporting and contradicting evidence are both present; "
                "manual reconciliation and source review are required."
            )
        if insufficient:
            unresolved_conflicts.append(
                "Some supplied sources did not contain sufficient evidence "
                "for the selected sub-question."
            )

        return EvidenceSummary(
            supporting_items=len(supporting),
            contradicting_items=len(contradicting),
            neutral_items=len(neutral),
            insufficient_items=len(insufficient),
            strongest_supporting_evidence=self._strongest(supporting),
            strongest_contradicting_evidence=self._strongest(contradicting),
            unresolved_conflicts=unresolved_conflicts,
        )

    @staticmethod
    def _items_with_stance(
        evidence_items: list[EvidenceItem],
        stance: EvidenceStance,
    ) -> list[EvidenceItem]:
        return [
            item
            for item in evidence_items
            if item.stance is stance
        ]

    def _strongest(
        self,
        evidence_items: list[EvidenceItem],
    ) -> EvidenceItem | None:
        if not evidence_items:
            return None
        return max(
            evidence_items,
            key=lambda item: self._STRENGTH_RANK[item.strength],
        )
