from collections.abc import Sequence

from app.schemas.evidence import (
    ConflictingSourceClaim,
    EvidenceConflictReport,
    EvidenceItem,
    EvidenceStance,
)
from app.schemas.investigation import InvestigationSubQuestion


class EvidenceConflictService:
    """Identify opposing source claims without producing a truth verdict."""

    def detect(
        self,
        sub_question: InvestigationSubQuestion,
        evidence_items: Sequence[EvidenceItem],
    ) -> EvidenceConflictReport:
        supporting = [
            item
            for item in evidence_items
            if item.stance is EvidenceStance.SUPPORTS
        ]
        contradicting = [
            item
            for item in evidence_items
            if item.stance is EvidenceStance.CONTRADICTS
        ]
        has_opposing_evidence = bool(supporting and contradicting)

        conflicting_claims = [
            ConflictingSourceClaim(
                supporting_evidence_id=support.evidence_id,
                supporting_source_id=support.provenance.source_id,
                contradicting_evidence_id=contradiction.evidence_id,
                contradicting_source_id=contradiction.provenance.source_id,
                description=(
                    "The supplied sources were classified in opposing "
                    "directions for the same sub-question; source review is "
                    "required."
                ),
            )
            for support in supporting
            for contradiction in contradicting
        ]
        unresolved_conflicts = (
            [
                "Supporting and contradicting source-grounded evidence are "
                "both present for this sub-question. The conflict remains "
                "unresolved and no truth verdict was generated."
            ]
            if has_opposing_evidence
            else []
        )

        return EvidenceConflictReport(
            sub_question_id=sub_question.id,
            has_supporting_and_contradicting_evidence=has_opposing_evidence,
            conflicting_source_claims=conflicting_claims,
            unresolved_conflicts=unresolved_conflicts,
        )
