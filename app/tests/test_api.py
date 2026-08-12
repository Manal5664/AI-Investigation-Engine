"""End-to-end tests for the EvidenceAI browser UI backed by FastAPI.

The UI now reads live data from the same persistence/document/vector/graph
stores as the /api/v1 pipeline, so these tests seed the engine repositories
directly and verify the pages and their JSON endpoints surface that data.

Run with:
    python -m pytest app/tests -v
"""

import asyncio
import itertools
import re
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database.provider import get_persistence_provider, reset_persistence
from app.documents.factory import get_document_store
from app.evidence.mock_extractor import MockEvidenceExtractor
from app.graph.factory import get_graph_store
from app.graph.models import GraphEdge, GraphNode, GraphRelationType, GraphNodeType
from app.main import app
from app.rag.vectorstore.factory import get_vector_store
from app.research.search.mock_provider import MockSearchProvider
from app.schemas.persistence import (
    ConflictRecord,
    EvidenceItemRecord,
    InvestigationRecord,
    InvestigationReportRecord,
    InvestigationStepRecord,
    SourceRecord,
)


async def _clear_stores() -> None:
    await get_document_store().clear()
    await get_graph_store().clear()
    await get_vector_store().clear()


@pytest.fixture(autouse=True)
def _fresh_state():
    asyncio.run(_clear_stores())
    reset_persistence()
    yield
    asyncio.run(_clear_stores())
    reset_persistence()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


_ID_COUNTER = itertools.count(1)


def seed_investigation(
    provider=None,
    *,
    query="Did the vendor overcharge for services in Q2?",
    status="completed",
) -> InvestigationRecord:
    """Persist a full investigation (header + steps + sources + evidence +
    conflicts + report) and return its record."""
    if provider is None:
        provider = get_persistence_provider()
    now = datetime.now(timezone.utc)
    investigation = InvestigationRecord(
        id="inv-%012x" % next(_ID_COUNTER),
        query=query,
        depth="quick",
        category="general_investigation",
        status=status,
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
            output_references=[investigation.id],
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
            summary="The clerk signed the disputed invoice.",
            rationale="Source documents the finding.",
            stance="supports",
            strength="strong",
            source_id="source-001",
            source_url="https://audit.example/working-paper",
            source_title="Audit working paper",
            retrieval_timestamp=now,
            relevant_passage="Jane Clerk signed the invoice on June 30.",
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
            has_supporting_and_contradicting_evidence=True,
            unresolved_conflicts=["One source says approved, another denies."],
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
        important_limitations=["Small sample size."],
        alternative_explanations=["Systemic rounding error."],
        evidence_gaps=["No ledger extract available."],
        created_at=now,
    )
    uow = provider.unit_of_work()
    try:
        uow.repositories.investigations.create(investigation)
        uow.repositories.investigations.save_steps(investigation.id, steps)
        uow.repositories.sources.save_many(investigation.id, sources)
        uow.repositories.evidence.save_items(investigation.id, evidence)
        uow.repositories.investigations.save_conflicts(
            investigation.id, conflicts
        )
        uow.repositories.investigations.save_report(investigation.id, report)
    finally:
        uow.commit()
        uow.close()
    return investigation


def agentic_body() -> dict:
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


def txt_bytes(text: str) -> bytes:
    return text.encode("utf-8")


# --------------------------------------------------------------------------
# Smoke tests
# --------------------------------------------------------------------------


def test_root_serves_service_info(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["message"] == "AI Investigation Engine is running successfully"


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_page_routes(client):
    for path in ("/dashboard", "/investigate", "/documents", "/history", "/rag", "/graph", "/app"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert b"EvidenceAI" in res.content


def test_pages_render_real_content(client):
    """Regression: every UI page must render page-specific HTML inside <main>,
    not a blank content area. HTTP 200 alone is not enough."""
    expected = {
        "/dashboard": (
            b"Dashboard",
            b"Investigations &amp; documents",
            b"Recent investigations",
            b'id="statTotal"',
        ),
        "/investigate": (
            b"New investigation",
            b"Investigation question",
            b"Run investigation",
            b'id="runCritic"',
            b'id="useRag"',
            b'id="useGraphRag"',
            b'id="depth"',
        ),
        "/documents": (
            b"Documents",
            b"Upload evidence",
            b"Stored documents",
            b"Upload evidence",
            b"Upload",
        ),
        "/history": (
            b"History",
            b"Past investigations and their outcomes.",
            b'id="historyBody"',
        ),
        "/rag": (
            b"Evidence search",
            b">Search<",
            b"Enter a question to search the evidence base.",
        ),
        "/graph": (
            b"Graph view",
            b"Inspector",
            b'id="graphCanvas"',
        ),
    }
    for path, markers in expected.items():
        res = client.get(path)
        assert res.status_code == 200, path
        # Page-specific content must be present (i.e. the content block
        # actually rendered inside <main> rather than an empty area).
        main = re.search(rb"<main.*?</main>", res.content, re.DOTALL)
        assert main is not None, path
        for marker in markers:
            assert marker in main.group(0), f"{path} missing {marker!r}"
        # Blank-page guard: strip tags from <main> and require real text.
        text = re.sub(rb"<[^>]+>", b" ", main.group(0))
        text = re.sub(rb"\s+", b" ", text).strip()
        assert len(text) > 40, f"{path} main content area is effectively empty"


def test_unknown_route_404(client):
    assert client.get("/nope").status_code == 404


# --------------------------------------------------------------------------
# Dashboard API
# --------------------------------------------------------------------------


def test_dashboard_summary(client):
    seed_investigation()
    upload = client.post(
        "/api/v1/documents/upload",
        files={
            "files": (
                "statement.txt",
                txt_bytes("The clerk signed the invoice."),
                "text/plain",
            )
        },
    )
    assert upload.status_code == 200

    res = client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["investigations"]["total"] == 1
    assert data["investigations"]["completed"] == 1
    assert data["investigations"]["total_documents"] == 1
    assert data["investigations_by_status"]["completed"] == 1
    assert data["sources"] == 1
    assert data["evidence"] == 1
    assert len(data["recent_investigations"]) == 1
    assert data["recent_investigations"][0]["query"].startswith(
        "Did the vendor overcharge"
    )
    assert len(data["trend_dates"]) == 14
    assert data["source_labels"] == ["text"]


def test_dashboard_empty(client):
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["investigations"]["total"] == 0
    assert data["recent_investigations"] == []
    assert data["source_labels"] == []
    assert data["rag"]["vector_count"] == 0
    assert data["graph"]["node_count"] == 0


# --------------------------------------------------------------------------
# History / investigation detail
# --------------------------------------------------------------------------


def test_history_uses_real_engine(client):
    seed_investigation(query="First case query")
    seed_investigation(
        get_persistence_provider(),
        query="Second case query",
    )
    res = client.get("/api/v1/investigations?limit=100")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 2
    queries = {item["query"] for item in payload["investigations"]}
    assert queries == {"First case query", "Second case query"}


def test_investigation_page_renders_real_data(client):
    investigation = seed_investigation()
    res = client.get(f"/investigation/{investigation.id}")
    assert res.status_code == 200
    body = res.content
    assert b"Did the vendor overcharge" in body
    assert b"Audit working paper" in body
    assert b"The clerk signed the disputed invoice." in body
    assert b"synthesis_produced" in body
    assert b"Material irregularities were identified." in body
    assert b"Export" in body


def test_investigation_page_missing(client):
    res = client.get("/investigation/inv-ffffffffffff")
    assert res.status_code == 404
    assert b"Investigation not found" in res.content


def test_delete_investigation_via_api(client):
    investigation = seed_investigation()
    res = client.delete(f"/api/v1/investigations/{investigation.id}")
    assert res.status_code == 200
    res = client.delete(f"/api/v1/investigations/{investigation.id}")
    assert res.status_code == 404


# --------------------------------------------------------------------------
# Investigation run (real agentic flow with mocked providers)
# --------------------------------------------------------------------------


def test_run_investigation_returns_id_and_persists(client):
    search_provider = MockSearchProvider()
    evidence_extractor = MockEvidenceExtractor()
    with (
        patch(
            "app.api.ui_routes.create_search_provider",
            return_value=search_provider,
        ),
        patch(
            "app.api.ui_routes.create_evidence_extractor",
            return_value=evidence_extractor,
        ),
    ):
        res = client.post("/api/investigations/run", json=agentic_body())
    assert res.status_code == 200
    payload = res.json()
    assert payload["investigation_id"].startswith("inv-")
    assert payload["status"] in {"completed", "partial", "failed"}

    listed = client.get("/api/v1/investigations")
    assert listed.json()["total"] == 1
    detail = client.get(f"/api/v1/investigations/{payload['investigation_id']}")
    assert detail.status_code == 200
    assert detail.json()["report"] is not None


def test_run_investigation_requires_query(client):
    res = client.post("/api/investigations/run", json={"query": "ab"})
    assert res.status_code == 422


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------


def test_export_csv(client):
    investigation = seed_investigation()
    res = client.get(f"/investigation/{investigation.id}/export?format=csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("Content-Type", "")
    assert "Audit working paper" in res.text
    assert "The clerk signed the disputed invoice." in res.text


def test_export_json(client):
    investigation = seed_investigation()
    res = client.get(f"/investigation/{investigation.id}/export?format=json")
    assert res.status_code == 200
    assert "application/json" in res.headers.get("Content-Type", "")
    payload = res.json()
    assert payload["investigation"]["id"] == investigation.id
    assert payload["report"]["overall_evidence_picture"]
    assert payload["steps"]
    assert payload["sources"]
    assert payload["evidence_items"]
    assert payload["conflicts"]


def test_export_missing_investigation(client):
    res = client.get("/investigation/inv-ffffffffffff/export?format=csv")
    assert res.status_code == 404


def test_export_bad_format(client):
    investigation = seed_investigation()
    res = client.get(f"/investigation/{investigation.id}/export?format=xml")
    assert res.status_code == 422


# --------------------------------------------------------------------------
# Documents (real engine endpoints)
# --------------------------------------------------------------------------


def test_documents_upload_and_list(client):
    res = client.post(
        "/api/v1/documents/upload",
        files={
            "files": (
                "statement.txt",
                txt_bytes("The clerk signed the invoice."),
                "text/plain",
            )
        },
    )
    assert res.status_code == 200
    uploaded = res.json()["documents"][0]["document"]
    assert uploaded["filename"] == "statement.txt"
    assert uploaded["kind"] == "text"

    listed = client.get("/api/v1/documents?limit=100")
    payload = listed.json()
    assert payload["total"] == 1
    assert payload["documents"][0]["document_id"] == uploaded["document_id"]
    assert payload["documents"][0]["page_count"] >= 1


def test_documents_delete(client):
    res = client.post(
        "/api/v1/documents/upload",
        files={
            "files": (
                "memo.txt",
                txt_bytes("Temporary evidence record."),
                "text/plain",
            )
        },
    )
    document_id = res.json()["documents"][0]["document"]["document_id"]
    deleted = client.delete(f"/api/v1/documents/{document_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    missing = client.delete(f"/api/v1/documents/{document_id}")
    assert missing.status_code == 404


# --------------------------------------------------------------------------
# RAG
# --------------------------------------------------------------------------


def test_rag_search_empty_index(client):
    res = client.post(
        "/api/v1/rag/search",
        json={"query": "who signed the invoice", "top_k": 5},
    )
    assert res.status_code == 200
    assert res.json() == []


def test_rag_stats(client):
    res = client.get("/api/v1/rag/stats")
    assert res.status_code == 200
    assert res.json()["vector_count"] == 0


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------


def test_graph_data_reflects_graph_store(client):
    async def seed():
        store = get_graph_store()
        node_a = GraphNode(
            node_id="inv-abcdef0123456789",
            node_type=GraphNodeType.INVESTIGATION,
            label="Vendor overpayment",
            metadata={"investigation_id": "inv-abcdef0123456789"},
        )
        node_b = GraphNode(
            node_id="source-001",
            node_type=GraphNodeType.SOURCE,
            label="Audit working paper",
            metadata={"investigation_id": "inv-abcdef0123456789"},
        )
        await store.add_node(node_a)
        await store.add_node(node_b)
        await store.add_edge(
            GraphEdge(
                edge_id="edge-001",
                source_node_id=node_a.node_id,
                target_node_id=node_b.node_id,
                relation_type=GraphRelationType.INVESTIGATES,
                confidence=0.9,
                metadata={"investigation_id": "inv-abcdef0123456789"},
            )
        )

    asyncio.run(seed())
    res = client.get("/api/graph")
    assert res.status_code == 200
    data = res.json()
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["edges"][0]["relation_type"] == "investigates"
    assert data["stats"]["node_count"] == 2
    assert data["stats"]["investigation_count"] == 1


def test_graph_data_empty(client):
    res = client.get("/api/graph")
    assert res.status_code == 200
    assert res.json()["nodes"] == []
    assert res.json()["edges"] == []


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------


def test_graceful_500():
    from fastapi import FastAPI

    from app.main import internal_error_handler

    mini = FastAPI()
    mini.add_exception_handler(Exception, internal_error_handler)

    @mini.get("/_boom")
    def boom():
        raise RuntimeError("kaboom")

    with TestClient(mini, raise_server_exceptions=False) as mini_client:
        res = mini_client.get("/_boom")
    assert res.status_code == 500
    payload = res.json()
    assert payload["code"] == "internal_error"
    assert "message" in payload
