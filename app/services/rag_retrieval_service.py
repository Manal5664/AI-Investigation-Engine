from app.rag.embeddings.base import EmbeddingProvider
from app.rag.retriever import SemanticRetriever
from app.rag.vectorstore.base import VectorStore
from app.schemas.rag import RetrievalRequest, RetrievalResult


class RAGRetrievalService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self._retriever = SemanticRetriever(
            embedding_provider,
            vector_store,
        )

    async def retrieve(
        self,
        request: RetrievalRequest,
    ) -> list[RetrievalResult]:
        return await self._retriever.retrieve(request)
