"""Persist finished agentic investigations into the repository layer.

One transaction writes the investigation header, its ordered audit steps,
all normalized sources, all evidence items (with flattened provenance),
conflict reports, and the synthesis report.
"""

from datetime import UTC, datetime

from app.database.provider import PersistenceProvider
from app.schemas.agentic import AgenticInvestigationResult, InvestigationState
from app.schemas.evidence import EvidenceItem
from app.schemas.persistence import (
    ConflictRecord,
    EvidenceItemRecord,
    InvestigationRecord,
    InvestigationReportRecord,
    InvestigationStepRecord,
    PersistenceStatus,
    SourceRecord,
)
from app.schemas.source import Source


class InvestigationPersistenceService:
    """Save an ``AgenticInvestigationResult`` under its aggregate ID."""

    def __init__(self, provider: PersistenceProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def save_result(
        self,
        result: AgenticInvestigationResult,
        *,
        user_id: str | None = None,
    ) -> str:
        state = result.state
        uow = self._provider.unit_of_work()
        try:
            investigation_id = self._allocate_id(state)
            uow.repositories.investigations.create(
                self._build_investigation(state, user_id, investigation_id)
            )
            uow.repositories.investigations.save_steps(
                investigation_id,
                self._build_steps(state),
            )
            uow.repositories.sources.save_many(
                investigation_id,
                self._build_sources(state),
            )
            uow.repositories.evidence.save_items(
                investigation_id,
                self._build_evidence(state),
            )
            uow.repositories.investigations.save_conflicts(
                investigation_id,
                self._build_conflicts(state),
            )
            uow.repositories.investigations.save_report(
                investigation_id,
                self._build_report(state),
            )
            uow.commit()
            return investigation_id
        except Exception:
            uow.rollback()
            raise
        finally:
            uow.close()

    @staticmethod
    def _allocate_id(state: InvestigationState) -> str:
        import hashlib
        import secrets

        digest = hashlib.sha256(
            state.query.encode("utf-8")
            + state.audit_trail[0].started_at.isoformat().encode("utf-8")
            + secrets.token_bytes(8)
        ).hexdigest()
        return f"inv-{digest[:16]}"

    def _build_investigation(
        self,
        state: InvestigationState,
        user_id: str | None,
        investigation_id: str,
    ) -> InvestigationRecord:
        steps = state.audit_trail
        created_at = (
            steps[0].started_at if steps else datetime.now(UTC)
        )
        completed_at = (
            steps[-1].completed_at if steps else None
        )
        provider_used = next(
            (step.provider_used for step in steps if step.provider_used),
            None,
        )
        model_used = next(
            (step.model_used for step in steps if step.model_used),
            None,
        )
        return InvestigationRecord(
            id=investigation_id,
            user_id=user_id,
            query=state.query,
            depth=state.depth,
            category=state.plan.category,
            status=PersistenceStatus(state.status),
            provider_used=provider_used,
            model_used=model_used,
            created_at=created_at,
            completed_at=completed_at,
            synthesis=state.synthesis.overall_evidence_picture,
            confidence=state.synthesis.confidence_level,
            warnings=list(state.warnings),
            errors=[
                error.model_dump(mode="json") for error in state.errors
            ],
            total_source_count=state.total_source_count,
            total_evidence_count=state.total_evidence_count,
            plan=state.plan.model_dump(mode="json"),
        )

    @staticmethod
    def _build_steps(state: InvestigationState) -> list[InvestigationStepRecord]:
        return [
            InvestigationStepRecord(
                step_id=step.step_id,
                step_name=step.step_name,
                status=step.status,
                step_order=index + 1,
                started_at=step.started_at,
                completed_at=step.completed_at,
                provider_used=step.provider_used,
                model_used=step.model_used,
                action_summary=step.action_summary,
                input_references=list(step.input_references),
                output_references=list(step.output_references),
                source_count=step.source_count,
                evidence_count=step.evidence_count,
                warnings=list(step.warnings),
                errors=[
                    error.model_dump(mode="json") for error in step.errors
                ],
            )
            for index, step in enumerate(state.audit_trail)
        ]

    @staticmethod
    def _build_sources(state: InvestigationState) -> list[SourceRecord]:
        collected: list[Source] = []
        for question_result in state.question_results:
            collected.extend(question_result.research.sources)
        collected.extend(state.critic_result.new_sources)
        seen: set[str] = set()
        records: list[SourceRecord] = []
        for source in collected:
            if source.source_id in seen:
                continue
            seen.add(source.source_id)
            records.append(
                SourceRecord(
                    source_id=source.source_id,
                    title=source.title,
                    url=str(source.url),
                    author=source.author,
                    publisher=source.publisher,
                    domain=source.domain,
                    published_at=source.published_at,
                    retrieved_at=source.retrieved_at,
                    source_type=source.source_type,
                    snippet=source.snippet,
                    metadata=source.metadata.model_dump(mode="json"),
                    credibility=(
                        source.credibility.model_dump(mode="json")
                        if source.credibility is not None
                        else None
                    ),
                )
            )
        return records

    @staticmethod
    def _build_evidence(state: InvestigationState) -> list[EvidenceItemRecord]:
        collected: list[EvidenceItem] = []
        for question_result in state.question_results:
            collected.extend(question_result.evidence_items)
        collected.extend(state.critic_result.new_evidence_items)
        source_titles = {
            source.source_id: source.title
            for source in InvestigationPersistenceService._build_sources(state)
        }
        seen: set[str] = set()
        records: list[EvidenceItemRecord] = []
        for item in collected:
            if item.evidence_id in seen:
                continue
            seen.add(item.evidence_id)
            provenance = item.provenance
            records.append(
                EvidenceItemRecord(
                    evidence_id=item.evidence_id,
                    sub_question_id=item.sub_question_id,
                    summary=item.summary,
                    rationale=item.rationale,
                    stance=item.stance,
                    strength=item.strength,
                    source_id=provenance.source_id,
                    source_url=str(provenance.source_url),
                    source_title=source_titles.get(provenance.source_id),
                    retrieval_timestamp=provenance.retrieval_timestamp,
                    relevant_passage=provenance.relevant_passage,
                    extraction_method=provenance.extraction_method,
                    model_used=provenance.model_used,
                    content_hash=provenance.content_hash,
                    page=provenance.page,
                    section=provenance.section,
                    location=provenance.location,
                )
            )
        return records

    @staticmethod
    def _build_conflicts(state: InvestigationState) -> list[ConflictRecord]:
        return [
            ConflictRecord(
                sub_question_id=conflict.sub_question_id,
                has_supporting_and_contradicting_evidence=(
                    conflict.has_supporting_and_contradicting_evidence
                ),
                unresolved_conflicts=list(conflict.unresolved_conflicts),
                conflicting_source_claims=[
                    claim.model_dump(mode="json")
                    for claim in conflict.conflicting_source_claims
                ],
            )
            for conflict in state.conflicts
        ]

    @staticmethod
    def _build_report(
        state: InvestigationState,
    ) -> InvestigationReportRecord:
        synthesis = state.synthesis
        completed_at = (
            state.audit_trail[-1].completed_at
            if state.audit_trail
            else datetime.now(UTC)
        )
        return InvestigationReportRecord(
            overall_evidence_picture=synthesis.overall_evidence_picture,
            confidence=synthesis.confidence_level,
            confidence_rationale=synthesis.confidence_rationale,
            strongest_supporting_evidence=(
                synthesis.strongest_supporting_evidence.model_dump(mode="json")
                if synthesis.strongest_supporting_evidence is not None
                else None
            ),
            strongest_contradicting_evidence=(
                synthesis.strongest_contradicting_evidence.model_dump(mode="json")
                if synthesis.strongest_contradicting_evidence is not None
                else None
            ),
            unresolved_conflicts=list(synthesis.unresolved_conflicts),
            important_limitations=list(synthesis.important_limitations),
            alternative_explanations=list(synthesis.alternative_explanations),
            evidence_gaps=list(synthesis.evidence_gaps),
            created_at=completed_at,
        )


__all__ = ["InvestigationPersistenceService"]
