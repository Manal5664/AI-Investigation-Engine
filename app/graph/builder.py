import hashlib
from collections.abc import Mapping, Sequence
from typing import ClassVar

from app.core.exceptions import ApplicationError
from app.graph.base import GraphStore
from app.graph.extraction.base import GraphExtractionResult
from app.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphProvenance,
    GraphRelationType,
)
from app.schemas.evidence import (
    EvidenceConflictReport,
    EvidenceItem,
    EvidenceStance,
    EvidenceStrength,
)
from app.schemas.graph import GraphBuildRequest, GraphBuildResult
from app.schemas.source import Source


class GraphBuilderError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            code="graph_builder_error",
            status_code=422,
        )


class GraphBuilder:
    """Deterministically build the knowledge graph for one investigation.

    Entity/relation extraction output is supplied by the caller; this builder
    only converts validated data into nodes and edges.
    """

    _STRENGTH_CONFIDENCE: ClassVar[dict[EvidenceStrength, float]] = {
        EvidenceStrength.STRONG: 1.0,
        EvidenceStrength.MODERATE: 0.75,
        EvidenceStrength.WEAK: 0.5,
        EvidenceStrength.UNKNOWN: 0.5,
    }

    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    async def build(
        self,
        request: GraphBuildRequest,
        extracted: Mapping[str, GraphExtractionResult],
    ) -> GraphBuildResult:
        sources = {source.source_id: source for source in request.sources}
        evidence_by_id = {
            item.evidence_id: item for item in request.evidence_items
        }
        self._validate_input(
            request,
            sources=sources,
            evidence_by_id=evidence_by_id,
            extracted=extracted,
        )

        nodes_added = 0
        edges_added = 0
        duplicates_skipped = 0

        investigation_node = self._investigation_node(request)
        if await self._store.add_node(investigation_node):
            nodes_added += 1
        else:
            duplicates_skipped += 1

        claims_built = 0
        sources_built = 0
        evidence_built = 0
        entities_extracted = 0
        relations_extracted = 0

        claims: dict[str, str] = {}
        for sub_question in request.sub_questions:
            claim_node = self._claim_node(request, sub_question)
            if await self._store.add_node(claim_node):
                nodes_added += 1
                claims_built += 1
            else:
                duplicates_skipped += 1
            claims[sub_question.id] = claim_node.node_id
            edge = self._edge(
                investigation_node.node_id,
                claim_node.node_id,
                GraphRelationType.INVESTIGATES,
                confidence=1.0,
                investigation_id=request.investigation_id,
                provenance=[
                    GraphProvenance(
                        description="investigation sub-question provenance"
                    )
                ],
            )
            if await self._store.add_edge(edge):
                edges_added += 1
            else:
                duplicates_skipped += 1

        source_nodes: dict[str, GraphNode] = {}
        for source in request.sources:
            source_node = self._source_node(request, source)
            if await self._store.add_node(source_node):
                nodes_added += 1
                sources_built += 1
            else:
                duplicates_skipped += 1
            source_nodes[source.source_id] = source_node

            publisher_node = self._publisher_node(source)
            if publisher_node is not None:
                if await self._store.add_node(publisher_node):
                    nodes_added += 1
                else:
                    duplicates_skipped += 1
                edge = self._edge(
                    source_node.node_id,
                    publisher_node.node_id,
                    GraphRelationType.PUBLISHED_BY,
                    confidence=1.0,
                    investigation_id=request.investigation_id,
                    provenance=[
                        GraphProvenance(
                            source_id=source.source_id,
                            url=str(source.url),
                            description="source publisher metadata",
                        )
                    ],
                )
                if await self._store.add_edge(edge):
                    edges_added += 1
                else:
                    duplicates_skipped += 1

            author_node = self._author_node(source)
            if author_node is not None:
                if await self._store.add_node(author_node):
                    nodes_added += 1
                else:
                    duplicates_skipped += 1
                edge = self._edge(
                    source_node.node_id,
                    author_node.node_id,
                    GraphRelationType.AUTHORED_BY,
                    confidence=1.0,
                    investigation_id=request.investigation_id,
                    provenance=[
                        GraphProvenance(
                            source_id=source.source_id,
                            url=str(source.url),
                            description="source author metadata",
                        )
                    ],
                )
                if await self._store.add_edge(edge):
                    edges_added += 1
                else:
                    duplicates_skipped += 1

        for evidence in request.evidence_items:
            evidence_node = self._evidence_node(request, evidence)
            if await self._store.add_node(evidence_node):
                nodes_added += 1
                evidence_built += 1
            else:
                duplicates_skipped += 1

            source_node = source_nodes.get(evidence.provenance.source_id)
            if source_node is not None:
                edge = self._edge(
                    evidence_node.node_id,
                    source_node.node_id,
                    GraphRelationType.DERIVED_FROM,
                    confidence=1.0,
                    investigation_id=request.investigation_id,
                    provenance=[
                        GraphProvenance(
                            source_id=evidence.provenance.source_id,
                            evidence_id=evidence.evidence_id,
                            url=str(evidence.provenance.source_url),
                            description="evidence provenance",
                        )
                    ],
                )
                if await self._store.add_edge(edge):
                    edges_added += 1
                else:
                    duplicates_skipped += 1

            claim_node_id = claims.get(evidence.sub_question_id)
            if claim_node_id is not None:
                relation, confidence = self._stance_relation(
                    evidence.stance,
                    evidence.strength,
                )
                edge = self._edge(
                    evidence_node.node_id,
                    claim_node_id,
                    relation,
                    confidence=confidence,
                    investigation_id=request.investigation_id,
                    provenance=[
                        GraphProvenance(
                            source_id=evidence.provenance.source_id,
                            evidence_id=evidence.evidence_id,
                            url=str(evidence.provenance.source_url),
                            description=(
                                "evidence stance classification "
                                f"({evidence.stance.value})"
                            ),
                        )
                    ],
                )
                if await self._store.add_edge(edge):
                    edges_added += 1
                else:
                    duplicates_skipped += 1

                cites_edge = self._edge(
                    claim_node_id,
                    source_node.node_id,
                    GraphRelationType.CITES,
                    confidence=confidence,
                    investigation_id=request.investigation_id,
                    provenance=[
                        GraphProvenance(
                            source_id=evidence.provenance.source_id,
                            evidence_id=evidence.evidence_id,
                            url=str(evidence.provenance.source_url),
                            description="claim cites grounding source",
                        )
                    ],
                )
                if await self._store.add_edge(cites_edge):
                    edges_added += 1
                else:
                    duplicates_skipped += 1

        for source_id, extraction in extracted.items():
            source_node = source_nodes.get(source_id)
            if source_node is None:
                continue
            source = sources[source_id]
            entity_nodes: dict[str, GraphNode] = {}
            for entity in extraction.entities:
                entity_node = self._entity_node(
                    entity.name,
                    entity.node_type,
                    entity.description,
                    source,
                )
                if await self._store.add_node(entity_node):
                    nodes_added += 1
                    entities_extracted += 1
                else:
                    duplicates_skipped += 1
                entity_nodes[entity.name.casefold()] = entity_node

                mentions_edge = self._edge(
                    source_node.node_id,
                    entity_node.node_id,
                    GraphRelationType.MENTIONS,
                    confidence=1.0,
                    investigation_id=request.investigation_id,
                    provenance=[
                        GraphProvenance(
                            source_id=source.source_id,
                            url=str(source.url),
                            description="extracted entity grounding",
                        )
                    ],
                )
                if await self._store.add_edge(mentions_edge):
                    edges_added += 1
                else:
                    duplicates_skipped += 1

            for relation in extraction.relations:
                source_entity = entity_nodes.get(
                    relation.source_name.casefold()
                )
                target_entity = entity_nodes.get(
                    relation.target_name.casefold()
                )
                if source_entity is None or target_entity is None:
                    raise GraphBuilderError(
                        "An extracted relation referenced an entity that was "
                        "not extracted from the same source."
                    )
                relations_extracted += 1
                edge = self._edge(
                    source_entity.node_id,
                    target_entity.node_id,
                    relation.relation_type,
                    confidence=relation.confidence,
                    investigation_id=request.investigation_id,
                    provenance=[
                        GraphProvenance(
                            source_id=source.source_id,
                            url=str(source.url),
                            description="extracted relation grounding",
                        )
                    ],
                )
                if await self._store.add_edge(edge):
                    edges_added += 1
                else:
                    duplicates_skipped += 1

        stats = await self._store.stats()
        return GraphBuildResult(
            investigation_id=request.investigation_id,
            nodes_added=nodes_added,
            edges_added=edges_added,
            duplicates_skipped=duplicates_skipped,
            claims_built=claims_built,
            sources_built=sources_built,
            evidence_built=evidence_built,
            entities_extracted=entities_extracted,
            relations_extracted=relations_extracted,
            warnings=self._input_warnings(
                request,
                extracted=extracted,
            ),
            stats=stats,
        )

    def _validate_input(
        self,
        request: GraphBuildRequest,
        *,
        sources: dict[str, Source],
        evidence_by_id: dict[str, EvidenceItem],
        extracted: Mapping[str, GraphExtractionResult],
    ) -> None:
        for item in request.evidence_items:
            source = sources.get(item.provenance.source_id)
            if source is None:
                raise GraphBuilderError(
                    f"Evidence {item.evidence_id} references unsupported "
                    f"source '{item.provenance.source_id}'."
                )
            if str(item.provenance.source_url) != str(source.url):
                raise GraphBuilderError(
                    f"Evidence {item.evidence_id} changed the URL of "
                    f"supplied source '{item.provenance.source_id}'."
                )
            if item.sub_question_id not in {
                question.id for question in request.sub_questions
            }:
                raise GraphBuilderError(
                    f"Evidence {item.evidence_id} references unsupported "
                    f"sub-question '{item.sub_question_id}'."
                )

        for report in request.conflicts:
            for claim in report.conflicting_source_claims:
                for evidence_id in (
                    claim.supporting_evidence_id,
                    claim.contradicting_evidence_id,
                ):
                    if evidence_id not in evidence_by_id:
                        raise GraphBuilderError(
                            f"Conflict report references unknown evidence "
                            f"'{evidence_id}'."
                        )
                for source_id in (
                    claim.supporting_source_id,
                    claim.contradicting_source_id,
                ):
                    if source_id not in sources:
                        raise GraphBuilderError(
                            f"Conflict report references unknown source "
                            f"'{source_id}'."
                        )

        for source_id in extracted:
            if source_id not in sources:
                raise GraphBuilderError(
                    f"Extraction output references unsupported source "
                    f"'{source_id}'."
                )

    @staticmethod
    def _input_warnings(
        request: GraphBuildRequest,
        *,
        extracted: Mapping[str, GraphExtractionResult],
    ) -> list[str]:
        warnings: list[str] = []
        source_ids = {source.source_id for source in request.sources}
        missing_extraction = source_ids - set(extracted)
        if missing_extraction:
            warnings.append(
                "Entity extraction was unavailable for "
                f"{len(missing_extraction)} source(s); only "
                "investigation, claim, source, and evidence structure was "
                "built for those sources."
            )
        return warnings

    def _investigation_node(self, request: GraphBuildRequest) -> GraphNode:
        return GraphNode(
            node_id=f"investigation-{request.investigation_id}",
            node_type=GraphNodeType.INVESTIGATION,
            label=request.query,
            description=(
                "Top-level investigation node for the supplied query."
            ),
            metadata={
                "investigation_id": request.investigation_id,
                "depth": request.depth.value,
            },
            provenance=[
                GraphProvenance(
                    description="investigation query provenance"
                )
            ],
        )

    def _claim_node(
        self,
        request: GraphBuildRequest,
        sub_question,
    ) -> GraphNode:
        return GraphNode(
            node_id=f"claim-{sub_question.id}",
            node_type=GraphNodeType.CLAIM,
            label=sub_question.question,
            description=sub_question.purpose,
            metadata={
                "investigation_id": request.investigation_id,
                "sub_question_id": sub_question.id,
                "priority": str(sub_question.priority),
            },
            provenance=[
                GraphProvenance(
                    description="investigation sub-question provenance"
                )
            ],
        )

    def _source_node(self, request: GraphBuildRequest, source: Source) -> GraphNode:
        return GraphNode(
            node_id=source.source_id,
            node_type=GraphNodeType.SOURCE,
            label=source.title,
            description=source.snippet or source.title,
            metadata={
                "investigation_id": request.investigation_id,
                "source_type": source.source_type.value,
                "domain": source.domain,
            },
            provenance=[
                GraphProvenance(
                    source_id=source.source_id,
                    url=str(source.url),
                    description="normalized source provenance",
                )
            ],
        )

    def _evidence_node(
        self,
        request: GraphBuildRequest,
        evidence: EvidenceItem,
    ) -> GraphNode:
        return GraphNode(
            node_id=evidence.evidence_id,
            node_type=GraphNodeType.EVIDENCE,
            label=evidence.summary,
            description=evidence.rationale,
            metadata={
                "investigation_id": request.investigation_id,
                "sub_question_id": evidence.sub_question_id,
                "stance": evidence.stance.value,
                "strength": evidence.strength.value,
            },
            provenance=[
                GraphProvenance(
                    source_id=evidence.provenance.source_id,
                    evidence_id=evidence.evidence_id,
                    url=str(evidence.provenance.source_url),
                    description="evidence provenance",
                )
            ],
        )

    def _publisher_node(self, source: Source) -> GraphNode | None:
        publisher = (source.publisher or "").strip()
        if not publisher:
            return None
        return GraphNode(
            node_id=self._entity_node_id(GraphNodeType.ORGANIZATION, publisher),
            node_type=GraphNodeType.ORGANIZATION,
            label=publisher,
            metadata={"source": "publisher_metadata"},
            provenance=[
                GraphProvenance(
                    source_id=source.source_id,
                    url=str(source.url),
                    description="source publisher metadata",
                )
            ],
        )

    def _author_node(self, source: Source) -> GraphNode | None:
        author = (source.author or "").strip()
        if not author:
            return None
        return GraphNode(
            node_id=self._entity_node_id(GraphNodeType.PERSON, author),
            node_type=GraphNodeType.PERSON,
            label=author,
            metadata={"source": "author_metadata"},
            provenance=[
                GraphProvenance(
                    source_id=source.source_id,
                    url=str(source.url),
                    description="source author metadata",
                )
            ],
        )

    def _entity_node(
        self,
        name: str,
        node_type: GraphNodeType,
        description: str | None,
        source: Source,
    ) -> GraphNode:
        return GraphNode(
            node_id=self._entity_node_id(node_type, name),
            node_type=node_type,
            label=name,
            description=description,
            metadata={"source": "extraction"},
            provenance=[
                GraphProvenance(
                    source_id=source.source_id,
                    url=str(source.url),
                    description="extracted entity grounding",
                )
            ],
        )

    @staticmethod
    def _entity_node_id(node_type: GraphNodeType, name: str) -> str:
        digest = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()
        return f"{node_type.value}-{digest[:12]}"

    @staticmethod
    def _edge(
        source_node_id: str,
        target_node_id: str,
        relation_type: GraphRelationType,
        *,
        confidence: float | None,
        investigation_id: str,
        provenance: Sequence[GraphProvenance],
    ) -> GraphEdge:
        digest = hashlib.sha256(
            (
                f"{source_node_id}|{relation_type.value}|{target_node_id}"
            ).encode("utf-8")
        ).hexdigest()
        return GraphEdge(
            edge_id=f"edge-{digest[:16]}",
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation_type=relation_type,
            confidence=confidence,
            provenance=list(provenance),
            metadata={"investigation_id": investigation_id},
        )

    def _stance_relation(
        self,
        stance: EvidenceStance,
        strength: EvidenceStrength,
    ) -> tuple[GraphRelationType, float]:
        confidence = self._STRENGTH_CONFIDENCE[strength]
        if stance is EvidenceStance.SUPPORTS:
            return GraphRelationType.SUPPORTS, confidence
        if stance is EvidenceStance.CONTRADICTS:
            return GraphRelationType.CONTRADICTS, confidence
        return GraphRelationType.RELATED_TO, 0.5
