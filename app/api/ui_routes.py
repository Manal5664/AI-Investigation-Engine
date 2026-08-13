"""Browser UI for the AI Investigation Engine.

Server-rendered pages plus the small JSON endpoints that back them. Every piece
of data is read live from the pluggable persistence provider and the
document/vector/graph stores used by the ``/api/v1`` pipeline — there is no
separate UI database. The only UI-specific endpoint is the dashboard aggregate
(``/api/dashboard``); interactive actions (run investigation, document
management, RAG search) call the real engine directly.
"""

from __future__ import annotations

import asyncio
import csv
import io

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.agents.critic_agent import CriticAgent
from app.agents.evidence_agent import EvidenceAgent
from app.agents.orchestrator import InvestigationOrchestrator
from app.agents.research_agent import ResearchAgent
from app.core.config import PROJECT_ROOT, settings
from app.database.provider import get_persistence_provider
from app.evidence.factory import create_evidence_extractor
from app.graph.extraction.factory import create_graph_extraction_provider
from app.graph.factory import get_graph_store
from app.rag.embeddings.factory import create_embedding_provider
from app.rag.vectorstore.factory import get_vector_store
from app.research.search.factory import create_search_provider
from app.schemas.agentic import AgenticInvestigationRequest
from app.schemas.persistence import (
    InvestigationDetailRecord,
    PersistenceStatus,
)
from app.services.graph_builder_service import GraphBuilderService
from app.services.graph_rag_service import GraphRAGService
from app.services.investigation_persistence_service import (
    InvestigationPersistenceService,
)
from app.services.rag_indexing_service import RAGIndexingService
from app.services.rag_retrieval_service import RAGRetrievalService

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))


def _render(
    request: Request,
    name: str,
    context: dict,
    *,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        name,
        {"request": request, "app_settings": settings, **context},
        status_code=status_code,
    )


def _error_page(
    request: Request,
    status_code: int,
    title: str,
    message: str,
):
    return _render(
        request,
        "error.html",
        {
            "error_code": status_code,
            "error_title": title,
            "error_message": message,
        },
        status_code=status_code,
    )


async def _run(fn):
    """Run a repository callback inside a unit of work.

    SQLAlchemy calls are marshalled onto a worker thread (the sync session
    must stay on one thread for its whole life); in-memory calls run inline.
    """
    provider = get_persistence_provider()
    if provider.requires_transaction:
        def run() -> object:
            uow = provider.unit_of_work()
            try:
                result = fn(uow)
                uow.commit()
                return result
            except Exception:
                uow.rollback()
                raise
            finally:
                uow.close()

        return await asyncio.to_thread(run)
    uow = provider.unit_of_work()
    try:
        return fn(uow)
    finally:
        uow.close()


async def _get_detail(
    investigation_id: str,
) -> InvestigationDetailRecord | None:
    return await _run(
        lambda uow: uow.repositories.investigations.get_detail(
            investigation_id
        )
    )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@router.get("/dashboard", include_in_schema=False)
async def dashboard_page(request: Request):
    return _render(request, "dashboard.html", {})


@router.get("/investigate", include_in_schema=False)
async def investigate_page(request: Request):
    return _render(request, "investigate.html", {})


@router.get("/documents", include_in_schema=False)
async def documents_page(request: Request):
    return _render(request, "documents.html", {})


@router.get("/history", include_in_schema=False)
async def history_page(request: Request):
    return _render(request, "history.html", {})


@router.get("/rag", include_in_schema=False)
async def rag_page(request: Request):
    return _render(request, "rag.html", {})


@router.get("/graph", include_in_schema=False)
async def graph_page(request: Request):
    stats = await get_graph_store().stats()
    return _render(request, "graph.html", {"graph_stats": stats})


@router.get("/app", include_in_schema=False)
async def app_home():
    return RedirectResponse("/dashboard", status_code=307)


@router.get("/investigation/{investigation_id}", include_in_schema=False)
async def investigation_page(request: Request, investigation_id: str):
    detail = await _get_detail(investigation_id)
    if detail is None:
        return _error_page(
            request,
            404,
            "Investigation not found",
            "The investigation you are looking for does not exist or has been deleted.",
        )
    return _render(request, "investigation.html", {"investigation": detail})


@router.get(
    "/investigation/{investigation_id}/export",
    include_in_schema=False,
)
async def export_investigation(
    investigation_id: str,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
):
    detail = await _get_detail(investigation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    if format == "json":
        return JSONResponse(
            {
                "investigation": detail.investigation.model_dump(
                    mode="json"
                ),
                "steps": [
                    step.model_dump(mode="json") for step in detail.steps
                ],
                "sources": [
                    source.model_dump(mode="json")
                    for source in detail.sources
                ],
                "evidence_items": [
                    item.model_dump(mode="json")
                    for item in detail.evidence_items
                ],
                "conflicts": [
                    conflict.model_dump(mode="json")
                    for conflict in detail.conflicts
                ],
                "report": (
                    detail.report.model_dump(mode="json")
                    if detail.report is not None
                    else None
                ),
            }
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["SECTION", "FIELD", "VALUE"])

    investigation = detail.investigation
    for key in (
        "id",
        "query",
        "depth",
        "category",
        "status",
        "provider_used",
        "model_used",
        "created_at",
        "completed_at",
        "confidence",
        "synthesis",
        "total_source_count",
        "total_evidence_count",
    ):
        writer.writerow(
            ["INVESTIGATION", key, getattr(investigation, key, "")]
        )
    writer.writerow([])

    for step in detail.steps:
        writer.writerow(
            ["STEP", "step", f"{step.step_name} ({step.status.value})"]
        )
        writer.writerow(["STEP", "status", step.status.value])
        writer.writerow(["STEP", "action_summary", step.action_summary])
        writer.writerow(["STEP", "started_at", step.started_at.isoformat()])
        writer.writerow(
            ["STEP", "completed_at", step.completed_at.isoformat()]
        )
        writer.writerow(["STEP", "sources", step.source_count])
        writer.writerow(["STEP", "evidence", step.evidence_count])
        writer.writerow([])

    for source in detail.sources:
        writer.writerow(["SOURCE", "title", source.title])
        writer.writerow(["SOURCE", "url", source.url])
        writer.writerow(["SOURCE", "domain", source.domain])
        writer.writerow(["SOURCE", "source_type", source.source_type.value])
        writer.writerow(["SOURCE", "snippet", source.snippet or ""])
        writer.writerow([])

    for item in detail.evidence_items:
        writer.writerow(["EVIDENCE", "summary", item.summary])
        writer.writerow(["EVIDENCE", "stance", item.stance.value])
        writer.writerow(["EVIDENCE", "strength", item.strength.value])
        writer.writerow(["EVIDENCE", "source_url", item.source_url])
        writer.writerow(
            ["EVIDENCE", "passage", item.relevant_passage]
        )
        writer.writerow([])

    for conflict in detail.conflicts:
        writer.writerow(
            [
                "CONFLICT",
                "sub_question_id",
                conflict.sub_question_id,
            ]
        )
        writer.writerow(
            [
                "CONFLICT",
                "has_supporting_and_contradicting_evidence",
                conflict.has_supporting_and_contradicting_evidence,
            ]
        )
        for unresolved in conflict.unresolved_conflicts:
            writer.writerow(["CONFLICT", "unresolved", unresolved])
        writer.writerow([])

    if detail.report is not None:
        writer.writerow(
            [
                "REPORT",
                "overall_evidence_picture",
                detail.report.overall_evidence_picture,
            ]
        )
        writer.writerow(
            ["REPORT", "confidence", detail.report.confidence.value]
        )
        writer.writerow(
            [
                "REPORT",
                "confidence_rationale",
                detail.report.confidence_rationale,
            ]
        )
        for gap in detail.report.evidence_gaps:
            writer.writerow(["REPORT", "evidence_gap", gap])

    return PlainTextResponse(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="investigation-{investigation_id}.csv"'
            )
        },
    )


# ---------------------------------------------------------------------------
# Dashboard aggregate
# ---------------------------------------------------------------------------


@router.get("/api/dashboard", include_in_schema=False)
async def dashboard_data():
    def work(uow):
        investigations = uow.repositories.investigations.list(
            limit=100,
            offset=0,
        )
        total = uow.repositories.investigations.count()
        documents = uow.repositories.documents.list(
            limit=100,
            offset=0,
        )
        document_total = uow.repositories.documents.count()
        return investigations, total, documents, document_total

    investigations, total, documents, document_total = await _run(work)

    by_status: dict[str, int] = {
        status.value: 0 for status in PersistenceStatus
    }
    for record in investigations:
        key = record.status.value
        by_status[key] = by_status.get(key, 0) + 1

    base_date = datetime.now(timezone.utc).date()
    trend_dates = [
        (base_date - timedelta(days=offset)).isoformat()
        for offset in range(13, -1, -1)
    ]
    trend_counts = {day: 0 for day in trend_dates}
    trend_document_counts = {day: 0 for day in trend_dates}
    for record in investigations:
        day = record.created_at.date().isoformat()
        if day in trend_counts:
            trend_counts[day] += 1
    for stored in documents:
        day = stored.uploaded.received_at.date().isoformat()
        if day in trend_document_counts:
            trend_document_counts[day] += 1

    kind_counts: dict[str, int] = {}
    for stored in documents:
        kind = stored.uploaded.kind.value
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    recent = [
        {
            "id": record.id,
            "query": record.query,
            "status": record.status.value,
            "depth": record.depth.value,
            "confidence": (
                record.confidence.value if record.confidence else None
            ),
            "created_at": record.created_at.isoformat(),
            "completed_at": (
                record.completed_at.isoformat()
                if record.completed_at is not None
                else None
            ),
            "sources": record.total_source_count,
            "evidence": record.total_evidence_count,
        }
        for record in investigations[:5]
    ]

    rag_stats, graph_stats = await asyncio.gather(
        get_vector_store().stats(),
        get_graph_store().stats(),
    )

    return {
        "investigations": {
            "total": total,
            "completed": by_status[PersistenceStatus.COMPLETED.value],
            "partial": by_status[PersistenceStatus.PARTIAL.value],
            "failed": by_status[PersistenceStatus.FAILED.value],
            "total_documents": document_total,
        },
        "investigations_by_status": by_status,
        "sources": sum(
            record.total_source_count for record in investigations
        ),
        "evidence": sum(
            record.total_evidence_count for record in investigations
        ),
        "recent_investigations": recent,
        "trend_dates": trend_dates,
        "trend_counts": [trend_counts[day] for day in trend_dates],
        "trend_document_counts": [
            trend_document_counts[day] for day in trend_dates
        ],
        "status_labels": [
            status.value for status in PersistenceStatus
        ],
        "status_counts": [
            by_status[status.value] for status in PersistenceStatus
        ],
        "source_labels": list(kind_counts.keys()),
        "source_counts": list(kind_counts.values()),
        "rag": {
            "vector_count": rag_stats.vector_count,
            "source_count": rag_stats.source_count,
            "vector_dimension": rag_stats.vector_dimension,
        },
        "graph": {
            "node_count": graph_stats.node_count,
            "edge_count": graph_stats.edge_count,
            "investigation_count": graph_stats.investigation_count,
        },
    }


# ---------------------------------------------------------------------------
# Run a real investigation (mirrors POST /api/v1/investigations/agentic
# but also returns the persisted investigation id so the UI can navigate).
# ---------------------------------------------------------------------------


@router.post("/api/investigations/run", include_in_schema=False)
async def run_investigation(request: AgenticInvestigationRequest):
    search_provider = create_search_provider()
    evidence_extractor = None
    embedding_provider = None
    graph_extraction_provider = None
    try:
        evidence_extractor = create_evidence_extractor()
        rag_indexing_service = None
        rag_retrieval_service = None
        if request.use_rag or request.use_graph_rag:
            embedding_provider = create_embedding_provider()
            vector_store = get_vector_store()
            rag_indexing_service = RAGIndexingService(
                embedding_provider,
                vector_store,
            )
            rag_retrieval_service = RAGRetrievalService(
                embedding_provider,
                vector_store,
            )
        graph_builder_service = None
        graph_rag_service = None
        if request.use_graph_rag:
            graph_extraction_provider = create_graph_extraction_provider()
            graph_store = get_graph_store()
            graph_builder_service = GraphBuilderService(
                graph_store,
                graph_extraction_provider,
            )
            graph_rag_service = GraphRAGService(
                rag_retrieval_service=rag_retrieval_service,
                graph_store=graph_store,
            )
        research_agent = ResearchAgent(search_provider)
        evidence_agent = EvidenceAgent(evidence_extractor)
        critic_agent = CriticAgent(
            research_agent=research_agent,
            evidence_agent=evidence_agent,
            rag_indexing_service=rag_indexing_service,
            rag_retrieval_service=rag_retrieval_service,
        )
        orchestrator = InvestigationOrchestrator(
            research_agent=research_agent,
            evidence_agent=evidence_agent,
            critic_agent=critic_agent,
            rag_indexing_service=rag_indexing_service,
            rag_retrieval_service=rag_retrieval_service,
            graph_builder_service=graph_builder_service,
            graph_rag_service=graph_rag_service,
        )
        result = await orchestrator.investigate(request)
        persistence_service = InvestigationPersistenceService(
            get_persistence_provider()
        )
        investigation_id = await asyncio.to_thread(
            persistence_service.save_result, result
        )
        return {
            "investigation_id": investigation_id,
            "status": result.status,
            "query": request.query,
        }
    finally:
        if graph_extraction_provider is not None:
            await graph_extraction_provider.aclose()
        if embedding_provider is not None:
            await embedding_provider.aclose()
        if evidence_extractor is not None:
            await evidence_extractor.aclose()
        await search_provider.aclose()


# ---------------------------------------------------------------------------
# Graph viewer data
# ---------------------------------------------------------------------------


@router.get("/api/graph", include_in_schema=False)
async def graph_data():
    store = get_graph_store()
    nodes = await store.find_nodes(limit=200)
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for node in nodes:
        neighbors = await store.get_neighbors(node.node_id, limit=100)
        for neighbor in neighbors:
            edge = neighbor.edge
            key = (
                edge.source_node_id,
                edge.relation_type.value,
                edge.target_node_id,
            )
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "id": edge.edge_id,
                    "source": edge.source_node_id,
                    "target": edge.target_node_id,
                    "relation_type": edge.relation_type.value,
                    "confidence": edge.confidence,
                    "investigation_id": edge.metadata.get(
                        "investigation_id"
                    ),
                }
            )
    return {
        "nodes": [
            {
                "id": node.node_id,
                "label": node.label,
                "node_type": node.node_type.value,
                "description": node.description,
                "investigation_id": node.metadata.get("investigation_id"),
            }
            for node in nodes
        ],
        "edges": edges,
        "stats": (await store.stats()).model_dump(mode="json"),
    }


__all__ = ["router"]
