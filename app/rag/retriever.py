import hashlib
from collections.abc import Sequence

from app.rag.embeddings.base import EmbeddingProvider
from app.rag.vectorstore.base import VectorStore
from app.schemas.rag import (
    IndexSource,
    RetrievalRequest,
    RetrievalResult,
)
from app.schemas.source import Source


class SemanticRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def retrieve(
        self,
        request: RetrievalRequest,
    ) -> list[RetrievalResult]:
        query_vector = await self._embedding_provider.embed_text(
            request.query
        )
        return await self._vector_store.similarity_search(
            query_vector,
            top_k=request.top_k,
            source_ids=(
                set(request.source_ids)
                if request.source_ids is not None
                else None
            ),
            source_urls=(
                {str(url) for url in request.source_urls}
                if request.source_urls is not None
                else None
            ),
        )


RAGRetriever = SemanticRetriever


def build_index_sources(sources: Sequence[Source]) -> list[IndexSource]:
    return [
        IndexSource(
            source_id=source.source_id,
            source_url=source.url,
            title=source.title,
            content=source.snippet or source.title,
            location=(
                "source.snippet"
                if source.snippet is not None
                else "source.title"
            ),
        )
        for source in sources
    ]


def grounded_sources_from_results(
    sources: Sequence[Source],
    results: Sequence[RetrievalResult],
    *,
    limit: int,
) -> list[Source]:
    known_sources = {
        (source.source_id, str(source.url)): source
        for source in sources
    }
    grounded_sources: list[Source] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        key = (result.source_id, str(result.source_url))
        source = known_sources.get(key)
        if source is None or key in seen:
            continue
        source_material = source.snippet or source.title
        expected_hash = hashlib.sha256(
            result.text.encode("utf-8")
        ).hexdigest()
        if (
            result.text not in source_material
            or result.metadata.content_hash != expected_hash
            or result.metadata.title != source.title
        ):
            continue
        grounded_sources.append(
            source.model_copy(update={"snippet": result.text})
        )
        seen.add(key)
        if len(grounded_sources) >= limit:
            break
    return grounded_sources
