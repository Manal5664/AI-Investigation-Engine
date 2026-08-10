from app.graph.base import GraphStore
from app.graph.builder import GraphBuilder
from app.graph.extraction.base import (
    GraphExtractionProvider,
    GraphExtractionProviderError,
    GraphExtractionResult,
)
from app.schemas.graph import GraphBuildRequest, GraphBuildResult
from app.schemas.source import Source


class GraphBuilderService:
    """Extract grounded entities/relations and build the knowledge graph."""

    def __init__(
        self,
        graph_store: GraphStore,
        extraction_provider: GraphExtractionProvider,
        builder: GraphBuilder | None = None,
    ) -> None:
        self._store = graph_store
        self._extraction_provider = extraction_provider
        self._builder = builder or GraphBuilder(graph_store)

    @property
    def provider_name(self) -> str:
        return self._extraction_provider.provider_name

    @property
    def model_name(self) -> str:
        return self._extraction_provider.model_name

    async def build(self, request: GraphBuildRequest) -> GraphBuildResult:
        extracted: dict[str, GraphExtractionResult] = {}
        warnings: list[str] = []
        for source in request.sources:
            result = await self._extract_source(source)
            if result is None:
                warnings.append(
                    f"Entity extraction was unavailable for "
                    f"{source.source_id}; structural graph connections were "
                    "still built for it."
                )
                continue
            extracted[source.source_id] = result

        result = await self._builder.build(request, extracted)
        return result.model_copy(
            update={"warnings": [*result.warnings, *warnings]}
        )

    async def _extract_source(
        self,
        source: Source,
    ) -> GraphExtractionResult | None:
        try:
            return await self._extraction_provider.extract_entities_and_relations(
                source_id=source.source_id,
                source_url=str(source.url),
                content=source.snippet or source.title,
            )
        except GraphExtractionProviderError:
            return None
