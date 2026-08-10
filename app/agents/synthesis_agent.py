from collections.abc import Sequence

from app.schemas.agentic import (
    CriticResult,
    SynthesisConfidence,
    SynthesisResult,
)
from app.schemas.evidence import (
    EvidenceConflictReport,
    EvidenceItem,
    EvidenceStance,
    EvidenceStrength,
    ProviderFailure,
)
from app.services.evidence_summary_service import EvidenceSummaryService


class SynthesisAgent:
    """Build a conservative evidence picture without a truth verdict."""

    def __init__(
        self,
        summary_service: EvidenceSummaryService | None = None,
    ) -> None:
        self._summary_service = summary_service or EvidenceSummaryService()

    def synthesize(
        self,
        *,
        query: str,
        evidence_items: Sequence[EvidenceItem],
        conflicts: Sequence[EvidenceConflictReport],
        critic_result: CriticResult,
        errors: Sequence[ProviderFailure],
        graph_context: Sequence[str] | None = None,
    ) -> SynthesisResult:
        del query
        items = list(evidence_items)
        summary = self._summary_service.summarize_items(items)
        supports = summary.supporting_items
        contradicts = summary.contradicting_items
        neutral = summary.neutral_items
        insufficient = summary.insufficient_items
        meaningful_count = supports + contradicts + neutral

        overall_picture = (
            "The bounded workflow identified "
            f"{supports} supporting, {contradicts} contradicting, "
            f"{neutral} neutral, and {insufficient} insufficient evidence "
            "item(s). These classifications describe the supplied evidence "
            "set and do not decide whether the original claim is true."
        )
        unresolved = list(summary.unresolved_conflicts)
        for report in conflicts:
            for conflict in report.unresolved_conflicts:
                if conflict not in unresolved:
                    unresolved.append(conflict)

        limitations = [
            "Evidence extraction was limited to source material supplied by "
            "the research provider, generally titles and snippets rather than "
            "complete documents."
        ]
        if errors:
            limitations.append(
                "One or more bounded agent actions failed, so the evidence "
                "picture is partial."
            )
        if insufficient:
            limitations.append(
                "Some supplied sources did not contain enough material for a "
                "directional evidence classification."
            )
        if not critic_result.enabled:
            limitations.append(
                "The devil's-advocate research step was disabled."
            )
        elif not critic_result.opposing_evidence_ids:
            limitations.append(
                "The bounded critic search found no new opposing evidence; "
                "that absence is an evidence gap, not confirmation."
            )
        if graph_context:
            limitations.append(
                "Graph retrieval added structural context about how the "
                "supplied sources, claims, and evidence relate to each "
                "other. It summarizes graph relationships only and does not "
                "change the evidence classifications above."
            )

        alternative_explanations = [
            "Differences in source scope, timeframe, definitions, or methods "
            "may explain divergent evidence classifications."
        ]
        if supports and contradicts:
            alternative_explanations.append(
                "The sources may describe different populations, conditions, "
                "or implementation contexts rather than the same proposition."
            )

        gaps: list[str] = []
        if not supports:
            gaps.append("No source was classified as supporting evidence.")
        if not contradicts:
            gaps.append(
                "No source was classified as genuine contradicting evidence."
            )
        if insufficient:
            gaps.append(
                "Additional source text is needed for items classified as "
                "insufficient."
            )
        if critic_result.enabled and not critic_result.new_sources:
            gaps.append(
                "The critic research round produced no new source material."
            )
        if not gaps:
            gaps.append(
                "Independent replication and full-document review remain "
                "outside this bounded workflow."
            )

        confidence = self._confidence(
            items,
            meaningful_count=meaningful_count,
            unresolved_conflicts=unresolved,
            has_errors=bool(errors),
        )
        confidence_rationale = (
            f"Confidence is {confidence.value} in the completeness and "
            "consistency of this evidence picture. It is not a probability "
            "that the investigated claim is true."
        )
        return SynthesisResult(
            overall_evidence_picture=overall_picture,
            strongest_supporting_evidence=(
                summary.strongest_supporting_evidence
            ),
            strongest_contradicting_evidence=(
                summary.strongest_contradicting_evidence
            ),
            unresolved_conflicts=unresolved,
            important_limitations=limitations,
            alternative_explanations=alternative_explanations,
            evidence_gaps=gaps,
            confidence_level=confidence,
            confidence_rationale=confidence_rationale,
        )

    @staticmethod
    def _confidence(
        evidence_items: Sequence[EvidenceItem],
        *,
        meaningful_count: int,
        unresolved_conflicts: Sequence[str],
        has_errors: bool,
    ) -> SynthesisConfidence:
        directional = [
            item
            for item in evidence_items
            if item.stance
            in {EvidenceStance.SUPPORTS, EvidenceStance.CONTRADICTS}
        ]
        if not evidence_items or not meaningful_count or not directional:
            return SynthesisConfidence.INSUFFICIENT
        if has_errors or unresolved_conflicts or meaningful_count < 2:
            return SynthesisConfidence.LOW
        strong_items = sum(
            item.strength is EvidenceStrength.STRONG
            for item in evidence_items
        )
        source_count = len(
            {item.provenance.source_url for item in evidence_items}
        )
        if meaningful_count >= 4 and strong_items >= 2 and source_count >= 4:
            return SynthesisConfidence.HIGH
        return SynthesisConfidence.MODERATE
