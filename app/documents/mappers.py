"""Map extracted document content into graph nodes and edges."""

from app.documents.models import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedSection,
)
from app.graph.models import (
    GraphEdge,
    GraphNode,
    GraphProvenance,
    GraphRelationType,
    GraphNodeType,
)


def _page_node_id(document_id: str, page_number: int) -> str:
    return f"{document_id}:page:{page_number}"


def _section_node_id(document_id: str, page_number: int, order_index: int) -> str:
    return f"{document_id}:page:{page_number}:section:{order_index}"


def _page_provenance(
    document: ExtractedDocument,
    page: ExtractedPage,
) -> GraphProvenance:
    return GraphProvenance(
        url=None,
        description=(
            f"{document.filename} page {page.page_number} "
            f"({document.extraction_method})"
        ),
    )


def build_page_nodes(
    document: ExtractedDocument,
) -> list[GraphNode]:
    """Create one EVIDENCE node per extracted page."""
    nodes: list[GraphNode] = []
    for page in document.pages:
        text = page.text.strip()
        if not text:
            continue
        nodes.append(
            GraphNode(
                node_id=_page_node_id(document.document_id, page.page_number),
                node_type=GraphNodeType.EVIDENCE,
                label=f"{document.filename} page {page.page_number}",
                description=text[:4000],
                metadata={
                    "document_id": document.document_id,
                    "page_number": str(page.page_number),
                    "extraction_method": document.extraction_method,
                },
                provenance=[_page_provenance(document, page)],
            )
        )
    return nodes


def build_page_edges(
    document: ExtractedDocument,
) -> list[GraphEdge]:
    """Chain page nodes so consecutive pages are graph-connected."""
    edges: list[GraphEdge] = []
    pages = [p for p in document.pages if p.text.strip()]
    for previous, current in zip(pages, pages[1:]):
        edges.append(
            GraphEdge(
                edge_id=(
                    f"{document.document_id}:page-edge:"
                    f"{previous.page_number}-{current.page_number}"
                ),
                source_node_id=_page_node_id(
                    document.document_id,
                    previous.page_number,
                ),
                target_node_id=_page_node_id(
                    document.document_id,
                    current.page_number,
                ),
                relation_type=GraphRelationType.RELATED_TO,
                confidence=1.0,
                provenance=[_page_provenance(document, current)],
                metadata={
                    "document_id": document.document_id,
                    "link_type": "consecutive_pages",
                },
            )
        )
    return edges


def build_section_nodes(
    document: ExtractedDocument,
) -> list[GraphNode]:
    """Create one TOPIC node per extracted section, linked to its page."""
    nodes: list[GraphNode] = []
    for page in document.pages:
        for section in page.sections:
            text = (section.text or "").strip()
            if not text:
                continue
            heading = section.heading or ""
            label = (
                heading[:120]
                if heading
                else f"{document.filename} section {section.order_index + 1}"
            )
            nodes.append(
                GraphNode(
                    node_id=_section_node_id(
                        document.document_id,
                        page.page_number,
                        section.order_index,
                    ),
                    node_type=GraphNodeType.TOPIC,
                    label=label,
                    description=text[:4000],
                    metadata={
                        "document_id": document.document_id,
                        "page_number": str(page.page_number),
                        "section_index": str(section.order_index),
                    },
                    provenance=[_page_provenance(document, page)],
                )
            )
    return nodes


def build_section_edges(
    document: ExtractedDocument,
) -> list[GraphEdge]:
    """Link every section TOPIC node to its containing EVIDENCE page node."""
    edges: list[GraphEdge] = []
    for page in document.pages:
        page_node_id = _page_node_id(
            document.document_id,
            page.page_number,
        )
        for section in page.sections:
            text = (section.text or "").strip()
            if not text:
                continue
            section_node_id = _section_node_id(
                document.document_id,
                page.page_number,
                section.order_index,
            )
            edges.append(
                GraphEdge(
                    edge_id=(
                        f"{document.document_id}:section-edge:"
                        f"{page.page_number}-{section.order_index}"
                    ),
                    source_node_id=section_node_id,
                    target_node_id=page_node_id,
                    relation_type=GraphRelationType.RELATED_TO,
                    confidence=1.0,
                    provenance=[_page_provenance(document, page)],
                    metadata={
                        "document_id": document.document_id,
                        "link_type": "section_of_page",
                    },
                )
            )
    return edges


def build_document_graph_nodes(document: ExtractedDocument) -> list[GraphNode]:
    return build_page_nodes(document) + build_section_nodes(document)


def build_document_graph_edges(document: ExtractedDocument) -> list[GraphEdge]:
    return build_page_edges(document) + build_section_edges(document)


__all__ = [
    "build_document_graph_edges",
    "build_document_graph_nodes",
    "build_page_edges",
    "build_page_nodes",
    "build_section_edges",
    "build_section_nodes",
]
