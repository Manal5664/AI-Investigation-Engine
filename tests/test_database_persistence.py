"""Tests for the Phase 10 persistence layer and its API surface."""

import asyncio
import hashlib
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from app.database.provider import (
    InMemoryPersistenceProvider,
    get_persistence_provider,
    reset_persistence,
)
from app.documents.factory import get_document_store
from app.evidence.mock_extractor import MockEvidenceExtractor
from app.graph.factory import get_graph_store
from app.main import app
from app.rag.vectorstore.factory import get_vector_store
from app.research.search.mock_provider import MockSearchProvider
from app.schemas.persistence import InvestigationRecord, UserRecord


def _txt_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


async def _clear_stores() -> None:
    await get_document_store().clear()
    await get_graph_store().clear()
    await get_vector_store().clear()


def _run(coro) -> None:
    asyncio.run(coro)


@pytest.fixture(autouse=True)
def _fresh_state():
    _run(_clear_stores())
    reset_persistence()
    yield
    _run(_clear_stores())
    reset_persistence()


def _agentic_body() -> dict:
    return {
        "query": "Research long-duration storage performance",
        "depth": "quick",
        "max_sub_questions": 1,
        "max_sources_per_question": 2,
        "run_critic": True,
        "max_critic_rounds": 1,
        "use_rag": False,
        "use_graph_rag": False,
    }


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


def test_provider_defaults_to_in_memory() -> None:
    provider = get_persistence_provider()
    assert isinstance(provider, InMemoryPersistenceProvider)
    assert provider.name == "in_memory"
    assert provider.requires_transaction is False


def test_reset_persistence_clears_repositories() -> None:
    provider = get_persistence_provider()
    uow = provider.unit_of_work()
    uow.repositories.investigations.create(
        InvestigationRecord(
            id="inv-abcdef0123456789",
            query="A sufficiently long investigation query",
            depth="quick",
            status="completed",
            created_at=datetime.now(timezone.utc),
            total_source_count=0,
            total_evidence_count=0,
        )
    )
    uow.commit()
    uow.close()
    assert provider.unit_of_work().repositories.investigations.count() == 1

    reset_persistence()
    assert provider.unit_of_work().repositories.investigations.count() == 0


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def test_user_create_get_and_duplicate_conflict() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            created = await client.post(
                "/api/v1/users",
                json={
                    "email": "analyst@example.com",
                    "display_name": "Analyst One",
                },
            )
            assert created.status_code == 200
            body = created.json()
            assert body["status"] == "completed"
            user_id = body["user"]["id"]
            assert user_id.startswith("user-")
            assert body["user"]["email"] == "analyst@example.com"

            duplicate = await client.post(
                "/api/v1/users",
                json={"email": "analyst@example.com"},
            )
            assert duplicate.status_code == 409

            fetched = await client.get(f"/api/v1/users/{user_id}")
            assert fetched.status_code == 200
            assert fetched.json()["user"]["display_name"] == "Analyst One"

            missing = await client.get("/api/v1/users/user-000000000000")
            assert missing.status_code == 404

    asyncio.run(exercise())


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def test_upload_persists_document_to_repository() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            upload = await client.post(
                "/api/v1/documents/upload",
                files={
                    "files": (
                        "report.txt",
                        _txt_bytes(
                            "Quarterly disclosure found material "
                            "irregularities in procurement."
                        ),
                        "text/plain",
                    )
                },
            )
            assert upload.status_code == 200
            document = upload.json()["documents"][0]["document"]
            document_id = document["document_id"]

            listed = await client.get("/api/v1/documents")
            assert listed.status_code == 200
            payload = listed.json()
            assert payload["status"] == "completed"
            assert payload["total"] == 1
            assert payload["documents"][0]["document_id"] == document_id
            assert payload["documents"][0]["content_hash"] == _sha256(
                _txt_bytes(
                    "Quarterly disclosure found material "
                    "irregularities in procurement."
                )
            )
            assert payload["documents"][0]["kind"] == "text"

            filtered = await client.get("/api/v1/documents?kind=text")
            assert filtered.json()["total"] == 1
            empty = await client.get("/api/v1/documents?kind=pdf")
            assert empty.json()["total"] == 0

    asyncio.run(exercise())


def test_persistence_get_fallback_for_cleared_store() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            upload = await client.post(
                "/api/v1/documents/upload",
                files={
                    "files": (
                        "ledger.txt",
                        _txt_bytes("Invoice reconciliation audit trail."),
                        "text/plain",
                    )
                },
            )
            document_id = upload.json()["documents"][0]["document"]["document_id"]

            await get_document_store().clear()
            store_has = await get_document_store().get(document_id)
            assert store_has is None

            fetched = await client.get(f"/api/v1/documents/{document_id}")
            assert fetched.status_code == 200
            assert fetched.json()["document"]["filename"] == "ledger.txt"

    asyncio.run(exercise())


def test_persistence_document_delete_removes_store_and_repo() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            upload = await client.post(
                "/api/v1/documents/upload",
                files={
                    "files": (
                        "temp.txt",
                        _txt_bytes("Temporary evidence record."),
                        "text/plain",
                    )
                },
            )
            document_id = upload.json()["documents"][0]["document"]["document_id"]

            deleted = await client.delete(f"/api/v1/documents/{document_id}")
            assert deleted.status_code == 200
            assert deleted.json()["deleted"] is True

            assert await get_document_store().get(document_id) is None
            assert (
                get_persistence_provider()
                .unit_of_work()
                .repositories.documents.get(document_id)
                is None
            )

            missing = await client.delete(f"/api/v1/documents/{document_id}")
            assert missing.status_code == 404

    asyncio.run(exercise())


# ---------------------------------------------------------------------------
# Investigations
# ---------------------------------------------------------------------------


def test_agentic_run_persists_investigation_to_repository() -> None:
    search_provider = MockSearchProvider()
    evidence_extractor = MockEvidenceExtractor()

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            with (
                patch(
                    "app.api.v1.routes.create_search_provider",
                    return_value=search_provider,
                ),
                patch(
                    "app.api.v1.routes.create_evidence_extractor",
                    return_value=evidence_extractor,
                ),
            ):
                response = await client.post(
                    "/api/v1/investigations/agentic",
                    json=_agentic_body(),
                )
            assert response.status_code == 200

            listed = await client.get("/api/v1/investigations")
            assert listed.status_code == 200
            payload = listed.json()
            assert payload["status"] == "completed"
            assert payload["total"] == 1
            summary = payload["investigations"][0]
            assert summary["query"] == "Research long-duration storage performance"
            assert summary["depth"] == "quick"
            assert summary["status"] in {"completed", "partial", "failed"}
            assert summary["created_at"]

            investigation_id = summary["id"]

            detail = await client.get(
                f"/api/v1/investigations/{investigation_id}"
            )
            assert detail.status_code == 200
            body = detail.json()
            assert body["investigation"]["id"] == investigation_id
            assert body["investigation"]["total_source_count"] >= 1
            assert body["investigation"]["total_evidence_count"] >= 1
            assert body["steps"]
            assert body["steps"][-1]["step_name"] == "synthesis_produced"
            assert body["sources"]
            assert body["evidence_items"]
            assert body["report"] is not None
            assert body["report"]["overall_evidence_picture"]

            deleted = await client.delete(
                f"/api/v1/investigations/{investigation_id}"
            )
            assert deleted.status_code == 200
            assert deleted.json()["deleted"] is True

            listed_after = await client.get("/api/v1/investigations")
            assert listed_after.json()["total"] == 0

            missing = await client.delete(
                f"/api/v1/investigations/{investigation_id}"
            )
            assert missing.status_code == 404

    asyncio.run(exercise())


# ---------------------------------------------------------------------------
# SQLAlchemy repositories (in-memory SQLite)
# ---------------------------------------------------------------------------


def _sqlalchemy_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _investigation_records() -> tuple:
    from app.schemas.persistence import (
        ConflictRecord,
        EvidenceItemRecord,
        InvestigationRecord,
        InvestigationReportRecord,
        InvestigationStepRecord,
        SourceRecord,
    )

    now = datetime.now(timezone.utc)
    investigation = InvestigationRecord(
        id="inv-abcdef0123456789",
        user_id="user-abcdef0123456789",
        query="A sufficiently long investigation query",
        depth="quick",
        category="research_topic",
        status="completed",
        provider_used="mock",
        model_used="mock-investigator",
        created_at=now,
        completed_at=now,
        synthesis="Material irregularities were identified.",
        confidence="high",
        warnings=[],
        errors=[],
        total_source_count=1,
        total_evidence_count=1,
        plan={"depth": "quick"},
    )
    steps = [
        InvestigationStepRecord(
            step_id="step-001",
            step_name="synthesis_produced",
            status="completed",
            step_order=1,
            started_at=now,
            completed_at=now,
            provider_used="mock",
            model_used="mock-investigator",
            action_summary="Synthesized the evidence base.",
            input_references=["evidence-001"],
            output_references=["inv-abcdef0123456789"],
            source_count=1,
            evidence_count=1,
            warnings=[],
            errors=[],
        )
    ]
    sources = [
        SourceRecord(
            source_id="source-001",
            title="Audit working paper",
            url="https://audit.example/working-paper",
            author="Lead Auditor",
            publisher="Example Audit Office",
            domain="audit.example",
            published_at=now,
            retrieved_at=now,
            source_type="academic",
            snippet="Irregularities found in invoice reconciliation.",
            metadata={"language": "en"},
            credibility=None,
        )
    ]
    evidence = [
        EvidenceItemRecord(
            evidence_id="evidence-001",
            sub_question_id="sq-01",
            summary="Irregularities in reconciliation.",
            rationale="Source documents the finding.",
            stance="supports",
            strength="strong",
            source_id="source-001",
            source_url="https://audit.example/working-paper",
            source_title="Audit working paper",
            retrieval_timestamp=now,
            relevant_passage="Irregularities found in invoice reconciliation.",
            extraction_method="llm",
            model_used="mock-evidence-extractor",
            content_hash="a" * 64,
            page=None,
            section=None,
            location=None,
        )
    ]
    conflicts = [
        ConflictRecord(
            sub_question_id="sq-01",
            has_supporting_and_contradicting_evidence=False,
            unresolved_conflicts=[],
            conflicting_source_claims=[],
        )
    ]
    report = InvestigationReportRecord(
        overall_evidence_picture="Material irregularities were identified.",
        confidence="high",
        confidence_rationale="Consistent primary-source support.",
        strongest_supporting_evidence={"summary": "Irregularities."},
        strongest_contradicting_evidence=None,
        unresolved_conflicts=[],
        important_limitations=[],
        alternative_explanations=[],
        evidence_gaps=[],
        created_at=now,
    )
    return investigation, steps, sources, evidence, conflicts, report


def test_route_helpers_work_with_transactional_provider() -> None:
    from sqlalchemy.orm import sessionmaker

    from app.database import models  # noqa: F401  (register tables)
    from app.database.base import Base
    from app.database.uow import SqlAlchemyUnitOfWork

    engine = _sqlalchemy_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    class _TransactionalProvider:
        name = "sqlalchemy"
        requires_transaction = True

        def unit_of_work(self):
            return SqlAlchemyUnitOfWork(factory)

    provider = _TransactionalProvider()

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            with patch(
                "app.api.v1.persistence_routes.get_persistence_provider",
                return_value=provider,
            ):
                created = await client.post(
                    "/api/v1/users",
                    json={
                        "email": "route-sql@example.com",
                        "display_name": "Route SQL",
                    },
                )
                assert created.status_code == 200

                fetched = await client.get(
                    f"/api/v1/users/{created.json()['user']['id']}"
                )
                assert fetched.status_code == 200
                assert (
                    fetched.json()["user"]["email"]
                    == "route-sql@example.com"
                )

                listed = await client.get("/api/v1/investigations")
                assert listed.status_code == 200
                assert listed.json()["total"] == 0

                listed = await client.get("/api/v1/documents")
                assert listed.status_code == 200
                assert listed.json()["total"] == 0

    asyncio.run(exercise())
    engine.dispose()


def test_agentic_run_persists_to_transactional_provider() -> None:
    from sqlalchemy.orm import sessionmaker

    from app.database import models  # noqa: F401  (register tables)
    from app.database.base import Base
    from app.database.uow import SqlAlchemyUnitOfWork

    engine = _sqlalchemy_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    class _TransactionalProvider:
        name = "sqlalchemy"
        requires_transaction = True

        def unit_of_work(self):
            return SqlAlchemyUnitOfWork(factory)

    provider = _TransactionalProvider()

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            with (
                patch(
                    "app.api.v1.routes.create_search_provider",
                    return_value=MockSearchProvider(),
                ),
                patch(
                    "app.api.v1.routes.create_evidence_extractor",
                    return_value=MockEvidenceExtractor(),
                ),
                patch(
                    "app.api.v1.routes.get_persistence_provider",
                    return_value=provider,
                ),
                patch(
                    "app.api.v1.persistence_routes.get_persistence_provider",
                    return_value=provider,
                ),
            ):
                response = await client.post(
                    "/api/v1/investigations/agentic",
                    json=_agentic_body(),
                )
                assert response.status_code == 200
                result = response.json()
                assert result["state"]["status"] in {
                    "completed",
                    "partial",
                }

                listed = await client.get("/api/v1/investigations")
                assert listed.status_code == 200
                payload = listed.json()
                assert payload["total"] == 1
                summary = payload["investigations"][0]
                assert summary["query"] == _agentic_body()["query"]

                detail = await client.get(
                    f"/api/v1/investigations/{summary['id']}"
                )
                assert detail.status_code == 200
                body = detail.json()
                assert body["investigation"]["id"] == summary["id"]
                assert body["steps"]
                assert body["steps"][-1]["step_name"] == "synthesis_produced"
                assert body["sources"]
                assert body["evidence_items"]
                assert body["report"] is not None

    asyncio.run(exercise())
    engine.dispose()


def test_sqlalchemy_repositories_round_trip() -> None:
    from sqlalchemy.orm import sessionmaker

    from app.database import models  # noqa: F401  (register tables)
    from app.database.base import Base
    from app.database.uow import SqlAlchemyUnitOfWork

    engine = _sqlalchemy_engine()
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    now = datetime.now(timezone.utc)
    user = UserRecord(
        id="user-abcdef0123456789",
        email="sql@example.com",
        display_name="SQL Analyst",
        created_at=now,
        updated_at=now,
        is_active=True,
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.repositories.users.create(user)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        fetched = uow.repositories.users.get("user-abcdef0123456789")
        assert fetched is not None
        assert fetched.email == "sql@example.com"

    investigation, steps, sources, evidence, conflicts, report = (
        _investigation_records()
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.repositories.investigations.create(investigation)
        uow.repositories.investigations.save_steps(
            investigation.id, steps
        )
        uow.repositories.sources.save_many(investigation.id, sources)
        uow.repositories.evidence.save_items(investigation.id, evidence)
        uow.repositories.investigations.save_conflicts(
            investigation.id, conflicts
        )
        uow.repositories.investigations.save_report(investigation.id, report)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        detail = uow.repositories.investigations.get_detail(investigation.id)
        assert detail is not None
        assert detail.investigation.query.startswith("A sufficiently")
        assert [step.step_name for step in detail.steps] == [
            "synthesis_produced"
        ]
        assert detail.sources[0].source_id == "source-001"
        assert detail.evidence_items[0].evidence_id == "evidence-001"
        assert detail.conflicts[0].has_supporting_and_contradicting_evidence is False
        assert detail.report is not None
        assert detail.report.overall_evidence_picture

        listed = uow.repositories.investigations.list(limit=10, offset=0)
        assert len(listed) == 1

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        deleted = uow.repositories.investigations.delete(investigation.id)
        assert deleted is True
        assert uow.repositories.investigations.count() == 0

    engine.dispose()
