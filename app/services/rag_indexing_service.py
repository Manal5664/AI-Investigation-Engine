from app.core.config import settings
from app.rag.chunking import DocumentChunker
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.vectorstore.base import VectorStore
from app.schemas.rag import IndexRequest, IndexResult


class RAGIndexingService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self._chunk_overlap = (
            settings.RAG_CHUNK_OVERLAP
            if chunk_overlap is None
            else chunk_overlap
        )

    async def index(self, request: IndexRequest) -> IndexResult:
        chunk_size = request.chunk_size or self._chunk_size
        chunk_overlap = (
            min(self._chunk_overlap, max(0, chunk_size - 1))
            if request.chunk_overlap is None
            else request.chunk_overlap
        )
        chunker = DocumentChunker(
            chunk_size=chunk_size,
            overlap=chunk_overlap,
        )

        sources_indexed = 0
        chunks_created = 0
        duplicates_skipped = 0
        failures = 0
        failure_details: list[str] = []
        vector_dimension: int | None = None

        for source in request.sources:
            try:
                chunks = chunker.chunk(source)
                vectors = await self._embedding_provider.embed_texts(
                    [chunk.text for chunk in chunks]
                )
                if vectors:
                    vector_dimension = len(vectors[0])
                write_result = await self._vector_store.add_chunks(
                    chunks,
                    vectors,
                )
            except Exception as exc:
                failures += 1
                failure_details.append(
                    f"{source.source_id}: {type(exc).__name__}"
                )
                continue

            chunks_created += write_result.added_count
            duplicates_skipped += write_result.duplicates_skipped
            if write_result.added_count:
                sources_indexed += 1

        return IndexResult(
            sources_indexed=sources_indexed,
            chunks_created=chunks_created,
            duplicates_skipped=duplicates_skipped,
            failures=failures,
            failure_details=failure_details,
            provider_used=self._embedding_provider.provider_name,
            model_used=self._embedding_provider.model_name,
            vector_store=self._vector_store.store_name,
            vector_dimension=(
                vector_dimension
                or self._embedding_provider.vector_dimension
            ),
        )
