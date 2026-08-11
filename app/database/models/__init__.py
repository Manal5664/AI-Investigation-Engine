"""Persistence models for Phase 10.

Every table keeps the application's external/schema IDs (``doc-...``,
``source-...``, ``evidence-...``, ``step-...``, ``inv-...``) as first-class
columns instead of replacing them with opaque database-only identifiers.
"""

from app.database.models.user import User
from app.database.models.investigation import Investigation
from app.database.models.investigation_step import InvestigationStep
from app.database.models.document import Document
from app.database.models.document_page import DocumentPage
from app.database.models.source import Source
from app.database.models.evidence_item import EvidenceItem
from app.database.models.conflict import Conflict
from app.database.models.investigation_report import InvestigationReport
from app.database.base import Base

__all__ = [
    "Base",
    "Conflict",
    "Document",
    "DocumentPage",
    "EvidenceItem",
    "Investigation",
    "InvestigationReport",
    "InvestigationStep",
    "Source",
    "User",
]
