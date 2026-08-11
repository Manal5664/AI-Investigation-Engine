"""Investigation service that answers queries strictly from stored documents."""

from app.documents.base import DocumentStore
from app.documents.reporting import (
    DocumentReportContext,
    DocumentReportGenerator,
    DocumentReportGeneratorError,
)
from app.graph.base import GraphStore
from app.schemas.documents import (
    DocumentExcerpt,
    DocumentInvestigationReport,
    DocumentInvestigationRequest,
    DocumentUsedRef,
)
from app.services.document_rag_service import DocumentRAGService
from app.services.investigation_service import InvestigationPlanner

MAX_EXCERPTS_PER_DOCUMENT = 6
MAX_GRAPH_NOTES = 20


class DocumentInvestigationService:
    """Plan an investigation and answer it from stored document pages."""

    def __init__(
        self,
        document_store: DocumentStore,
        generator: DocumentReportGenerator,
        rag_service: DocumentRAGService,
        graph_store: GraphStore | None = None,
    ) -> None:
        self._document_store = document_store
        self._generator = generator
        self._rag_service = rag_service
        self._graph_store = graph_store
        self._planner = InvestigationPlanner()

    async def investigate(
        self,
        request: DocumentInvestigationRequest,
    ) -> DocumentInvestigationReport:
        documents = await self._target_documents(request)
        if not documents:
            return DocumentInvestigationReport(
                status="no_documents",
                query=request.query,
                depth=request.depth,
                category=self._planner.detect_category(request.query),
                findings=["No documents are stored for this investigation."],
                provider_used=self._generator.provider_name,
                model_used=self._generator.model_name,
                fallback_used=False,
            )

        plan = self._planner.plan(request)
        excerpts, documents_used = await self._collect_excerpts(
            documents,
            request.query,
            request.use_rag,
        )
        graph_notes = await self._collect_graph_notes(
            documents,
            request.use_graph,
        )

        context = DocumentReportContext(
            query=request.query,
            plan=plan,
            excerpts=excerpts,
            documents_used=documents_used,
            graph_notes=graph_notes,
        )
        try:
            payload = await self._generator.generate(context)
            return DocumentInvestigationReport.model_validate(payload)
        except DocumentReportGeneratorError:
            raise
        except Exception as exc:
            raise DocumentReportGeneratorError(
                f"report generation failed ({type(exc).__name__})."
            ) from exc

    async def _target_documents(
        self,
        request: DocumentInvestigationRequest,
    ):
        if request.document_ids is None:
            return await self._document_store.list_all(limit=1000)
        return await self._document_store.get_many(request.document_ids)

    async def _collect_excerpts(
        self,
        documents,
        query: str,
        use_rag: bool,
    ) -> tuple[list[DocumentExcerpt], list[DocumentUsedRef]]:
        documents_by_id = {
            stored.uploaded.document_id: stored for stored in documents
        }
        documents_used = [
            DocumentUsedRef(
                document_id=stored.uploaded.document_id,
                filename=stored.uploaded.filename,
                page_count=stored.extracted.page_count,
            )
            for stored in documents
        ]

        relevant = []
        if use_rag:
            relevant = await self._rag_service.find_relevant_pages(
                query,
                limit=MAX_EXCERPTS_PER_DOCUMENT * len(documents),
                document_ids=list(documents_by_id),
            )

        excerpts: list[DocumentExcerpt] = []
        used_pages: dict[str, set[int]] = {}

        def add_excerpt(document_id, filename, page_number, text) -> None:
            if len([e for e in excerpts if e.document_id == document_id]) >= (
                MAX_EXCERPTS_PER_DOCUMENT
            ):
                return
            excerpts.append(
                DocumentExcerpt(
                    document_id=document_id,
                    filename=filename,
                    page_number=page_number,
                    text=text,
                )
            )
            used_pages.setdefault(document_id, set()).add(page_number)

        if relevant:
            for page in relevant:
                stored = documents_by_id.get(page.document_id)
                if stored is None:
                    continue
                for extracted_page in stored.extracted.pages:
                    if extracted_page.page_number != page.page_number:
                        continue
                    if not extracted_page.text.strip():
                        continue
                    add_excerpt(
                        stored.uploaded.document_id,
                        stored.uploaded.filename,
                        page.page_number,
                        extracted_page.text,
                    )
                    break

        if not excerpts:
            for stored in documents:
                for extracted_page in stored.extracted.pages:
                    if not extracted_page.text.strip():
                        continue
                    add_excerpt(
                        stored.uploaded.document_id,
                        stored.uploaded.filename,
                        extracted_page.page_number,
                        extracted_page.text,
                    )
                    if (
                        len(
                            [
                                e
                                for e in excerpts
                                if e.document_id == stored.uploaded.document_id
                            ]
                        )
                        >= MAX_EXCERPTS_PER_DOCUMENT
                    ):
                        break

        for ref in documents_used:
            ref.pages_used = sorted(used_pages.get(ref.document_id, set()))
        return excerpts, documents_used

    async def _collect_graph_notes(
        self,
        documents,
        use_graph: bool,
    ) -> list[str]:
        if not use_graph or self._graph_store is None:
            return []
        notes: list[str] = []
        for stored in documents:
            for page in stored.extracted.pages:
                node_id = (
                    f"{stored.uploaded.document_id}:page:{page.page_number}"
                )
                try:
                    neighbors = await self._graph_store.get_neighbors(
                        node_id,
                        direction="both",
                        limit=10,
                    )
                except Exception:
                    continue
                for neighbor in neighbors:
                    if neighbor.direction == "in":
                        continue
                    notes.append(
                        f"{stored.uploaded.filename} page {page.page_number} "
                        f"links to '{neighbor.node.label}' via "
                        f"{neighbor.edge.relation_type.value}."
                    )
                    if len(notes) >= MAX_GRAPH_NOTES:
                        return notes
        return notes


__all__ = ["DocumentInvestigationService"]
