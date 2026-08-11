"""Conversions between domain records and SQLAlchemy ORM models."""

from app.database.models import (
    Conflict,
    Document,
    DocumentPage,
    EvidenceItem,
    Investigation,
    InvestigationReport,
    InvestigationStep,
    Source,
    User,
)
from app.documents.models import (
    DocumentKind,
    ExtractedDocument,
    ExtractedImageContent,
    ExtractedPage,
    ExtractedSection,
    StoredDocument,
    UploadedDocument,
)
from app.schemas.persistence import (
    ConflictRecord,
    EvidenceItemRecord,
    InvestigationRecord,
    InvestigationReportRecord,
    InvestigationStepRecord,
    SourceRecord,
    UserRecord,
)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


def user_model_to_record(model: User) -> UserRecord:
    return UserRecord(
        id=model.id,
        email=model.email,
        display_name=model.display_name or "",
        created_at=model.created_at,
        updated_at=model.updated_at,
        is_active=model.is_active,
    )


def user_record_to_model(record: UserRecord) -> User:
    return User(
        id=record.id,
        email=record.email,
        display_name=record.display_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
        is_active=record.is_active,
    )


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


def stored_document_to_model(stored: StoredDocument) -> Document:
    uploaded = stored.uploaded
    extracted = stored.extracted
    pages = [
        DocumentPage(
            page_number=page.page_number,
            text=page.text,
            requires_vision=page.requires_vision,
            sections=[section.model_dump(mode="json") for section in page.sections],
        )
        for page in extracted.pages
    ]
    return Document(
        id=uploaded.document_id,
        filename=uploaded.filename,
        mime_type=uploaded.mime_type,
        file_size_bytes=uploaded.file_size_bytes,
        content_hash=uploaded.content_hash,
        kind=uploaded.kind.value,
        extension=uploaded.extension,
        extraction_method=extracted.extraction_method,
        page_count=extracted.page_count,
        character_count=extracted.character_count,
        requires_vision_pages=sum(
            1 for page in extracted.pages if page.requires_vision
        ),
        received_at=uploaded.received_at,
        extracted_at=extracted.extracted_at,
        warnings=list(extracted.warnings),
        content=stored.content,
        image_content=(
            extracted.image_content.model_dump(mode="json")
            if extracted.image_content is not None
            else None
        ),
        pages=pages,
    )


def document_model_to_stored(model: Document) -> StoredDocument:
    uploaded = UploadedDocument(
        document_id=model.id,
        filename=model.filename,
        mime_type=model.mime_type,
        file_size_bytes=model.file_size_bytes,
        content_hash=model.content_hash,
        kind=DocumentKind(model.kind),
        extension=model.extension,
        received_at=model.received_at,
    )
    ordered_pages = sorted(model.pages, key=lambda page: page.page_number)
    pages = [
        ExtractedPage(
            page_number=page.page_number,
            text=page.text,
            requires_vision=page.requires_vision,
            sections=[
                ExtractedSection.model_validate(section)
                for section in (page.sections or [])
            ],
        )
        for page in ordered_pages
    ]
    extracted = ExtractedDocument(
        document_id=model.id,
        filename=model.filename,
        mime_type=model.mime_type,
        file_size_bytes=model.file_size_bytes,
        content_hash=model.content_hash,
        kind=DocumentKind(model.kind),
        extraction_method=model.extraction_method,
        extracted_at=model.extracted_at,
        pages=pages,
        image_content=(
            ExtractedImageContent.model_validate(model.image_content)
            if model.image_content is not None
            else None
        ),
        warnings=list(model.warnings or []),
    )
    return StoredDocument(
        uploaded=uploaded,
        extracted=extracted,
        content=model.content or b"",
    )


# ---------------------------------------------------------------------------
# Investigation aggregate
# ---------------------------------------------------------------------------


def investigation_model_to_record(model: Investigation) -> InvestigationRecord:
    return InvestigationRecord(
        id=model.id,
        user_id=model.user_id,
        query=model.query,
        depth=model.depth,
        category=model.category,
        status=model.status,
        provider_used=model.provider_used,
        model_used=model.model_used,
        created_at=model.created_at,
        completed_at=model.completed_at,
        synthesis=model.synthesis,
        confidence=model.confidence,
        warnings=list(model.warnings or []),
        errors=list(model.errors or []),
        total_source_count=model.total_source_count,
        total_evidence_count=model.total_evidence_count,
        plan=model.plan,
    )


def investigation_record_to_model(record: InvestigationRecord) -> Investigation:
    return Investigation(
        id=record.id,
        user_id=record.user_id,
        query=record.query,
        depth=record.depth,
        category=(
            record.category.value if record.category is not None else None
        ),
        status=record.status,
        provider_used=record.provider_used,
        model_used=record.model_used,
        created_at=record.created_at,
        completed_at=record.completed_at,
        synthesis=record.synthesis,
        confidence=(
            record.confidence.value if record.confidence is not None else None
        ),
        warnings=list(record.warnings),
        errors=list(record.errors),
        total_source_count=record.total_source_count,
        total_evidence_count=record.total_evidence_count,
        plan=record.plan,
    )


def step_model_to_record(model: InvestigationStep) -> InvestigationStepRecord:
    return InvestigationStepRecord(
        step_id=model.step_id,
        step_name=model.step_name,
        status=model.status,
        step_order=model.step_order,
        started_at=model.started_at,
        completed_at=model.completed_at,
        provider_used=model.provider_used,
        model_used=model.model_used,
        action_summary=model.action_summary,
        input_references=list(model.input_references or []),
        output_references=list(model.output_references or []),
        source_count=model.source_count,
        evidence_count=model.evidence_count,
        warnings=list(model.warnings or []),
        errors=list(model.errors or []),
    )


def step_record_to_model(
    investigation_id: str,
    record: InvestigationStepRecord,
) -> InvestigationStep:
    return InvestigationStep(
        investigation_id=investigation_id,
        step_id=record.step_id,
        step_name=record.step_name,
        status=record.status,
        step_order=record.step_order,
        started_at=record.started_at,
        completed_at=record.completed_at,
        provider_used=record.provider_used,
        model_used=record.model_used,
        action_summary=record.action_summary,
        input_references=list(record.input_references),
        output_references=list(record.output_references),
        source_count=record.source_count,
        evidence_count=record.evidence_count,
        warnings=list(record.warnings),
        errors=list(record.errors),
    )


def source_model_to_record(model: Source) -> SourceRecord:
    return SourceRecord(
        source_id=model.source_id,
        title=model.title,
        url=model.url,
        author=model.author,
        publisher=model.publisher,
        domain=model.domain,
        published_at=model.published_at,
        retrieved_at=model.retrieved_at,
        source_type=model.source_type,
        snippet=model.snippet,
        metadata=dict(model.metadata_ or {}),
        credibility=model.credibility,
    )


def source_record_to_model(
    investigation_id: str,
    record: SourceRecord,
) -> Source:
    return Source(
        investigation_id=investigation_id,
        source_id=record.source_id,
        title=record.title,
        url=record.url,
        author=record.author,
        publisher=record.publisher,
        domain=record.domain,
        published_at=record.published_at,
        retrieved_at=record.retrieved_at,
        source_type=record.source_type.value,
        snippet=record.snippet,
        metadata_=dict(record.metadata),
        credibility=record.credibility,
    )


def evidence_model_to_record(model: EvidenceItem) -> EvidenceItemRecord:
    return EvidenceItemRecord(
        evidence_id=model.evidence_id,
        sub_question_id=model.sub_question_id,
        summary=model.summary,
        rationale=model.rationale,
        stance=model.stance,
        strength=model.strength,
        source_id=model.source_id,
        source_url=model.source_url,
        source_title=model.source_title,
        retrieval_timestamp=model.retrieval_timestamp,
        relevant_passage=model.relevant_passage,
        extraction_method=model.extraction_method,
        model_used=model.model_used,
        content_hash=model.content_hash,
        page=model.page,
        section=model.section,
        location=model.location,
    )


def evidence_record_to_model(
    investigation_id: str,
    record: EvidenceItemRecord,
) -> EvidenceItem:
    return EvidenceItem(
        investigation_id=investigation_id,
        evidence_id=record.evidence_id,
        sub_question_id=record.sub_question_id,
        summary=record.summary,
        rationale=record.rationale,
        stance=record.stance.value,
        strength=record.strength.value,
        source_id=record.source_id,
        source_url=record.source_url,
        source_title=record.source_title,
        retrieval_timestamp=record.retrieval_timestamp,
        relevant_passage=record.relevant_passage,
        extraction_method=record.extraction_method,
        model_used=record.model_used,
        content_hash=record.content_hash,
        page=record.page,
        section=record.section,
        location=record.location,
    )


def conflict_model_to_record(model: Conflict) -> ConflictRecord:
    return ConflictRecord(
        sub_question_id=model.sub_question_id,
        has_supporting_and_contradicting_evidence=(
            model.has_supporting_and_contradicting_evidence
        ),
        unresolved_conflicts=list(model.unresolved_conflicts or []),
        conflicting_source_claims=list(model.conflicting_source_claims or []),
    )


def conflict_record_to_model(
    investigation_id: str,
    record: ConflictRecord,
) -> Conflict:
    return Conflict(
        investigation_id=investigation_id,
        sub_question_id=record.sub_question_id,
        has_supporting_and_contradicting_evidence=(
            record.has_supporting_and_contradicting_evidence
        ),
        unresolved_conflicts=list(record.unresolved_conflicts),
        conflicting_source_claims=list(record.conflicting_source_claims),
    )


def report_model_to_record(
    model: InvestigationReport,
) -> InvestigationReportRecord:
    return InvestigationReportRecord(
        overall_evidence_picture=model.overall_evidence_picture,
        confidence=model.confidence,
        confidence_rationale=model.confidence_rationale or "",
        strongest_supporting_evidence=model.strongest_supporting_evidence,
        strongest_contradicting_evidence=model.strongest_contradicting_evidence,
        unresolved_conflicts=list(model.unresolved_conflicts or []),
        important_limitations=list(model.important_limitations or []),
        alternative_explanations=list(model.alternative_explanations or []),
        evidence_gaps=list(model.evidence_gaps or []),
        created_at=model.created_at,
    )


def report_record_to_model(
    investigation_id: str,
    record: InvestigationReportRecord,
) -> InvestigationReport:
    return InvestigationReport(
        investigation_id=investigation_id,
        overall_evidence_picture=record.overall_evidence_picture,
        confidence=record.confidence.value,
        confidence_rationale=record.confidence_rationale,
        strongest_supporting_evidence=record.strongest_supporting_evidence,
        strongest_contradicting_evidence=record.strongest_contradicting_evidence,
        unresolved_conflicts=list(record.unresolved_conflicts),
        important_limitations=list(record.important_limitations),
        alternative_explanations=list(record.alternative_explanations),
        evidence_gaps=list(record.evidence_gaps),
        created_at=record.created_at,
    )


__all__ = [
    "conflict_model_to_record",
    "conflict_record_to_model",
    "document_model_to_stored",
    "evidence_model_to_record",
    "evidence_record_to_model",
    "investigation_model_to_record",
    "investigation_record_to_model",
    "report_model_to_record",
    "report_record_to_model",
    "source_model_to_record",
    "source_record_to_model",
    "step_model_to_record",
    "step_record_to_model",
    "stored_document_to_model",
    "user_model_to_record",
    "user_record_to_model",
]
