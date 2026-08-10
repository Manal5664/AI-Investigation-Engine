import asyncio
import hashlib
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.main import app
from app.rag.chunking import DocumentChunker
from app.rag.embeddings.gemini_provider import GeminiEmbeddingProvider
from app.rag.embeddings.mock_provider import MockEmbeddingProvider
from app.rag.vectorstore.base import cosine_similarity
from app.rag.vectorstore.factory import get_vector_store
from app.rag.vectorstore.in_memory import InMemoryVectorStore
from app.schemas.rag import (
    IndexRequest,
    IndexSource,
    RetrievalRequest,
)
from app.services.rag_indexing_service import RAGIndexingService
from app.services.rag_retrieval_service import RAGRetrievalService


def _source(
    source_id: str,
    content: str,
    *,
    url: str | None = None,
    title: str | None = None,
) -> IndexSource:
    return IndexSource(
        source_id=source_id,
        source_url=url or f"https://{source_id}.example/report",
        title=title or f"Title for {source_id}",
        content=content,
        section="findings",
        location="body",
    )


def test_chunking_is_deterministic_word_aware_and_preserves_overlap() -> None:
    source = _source(
        "source-001",
        (
            "alpha beta gamma delta epsilon zeta eta theta iota kappa "
            "lambda mu nu xi omicron pi rho sigma"
        ),
    )
    chunker = DocumentChunker(chunk_size=40, overlap=12)

    first = chunker.chunk(source)
    second = chunker.chunk(source)

    assert first == second
    assert len(first) > 1
    assert all(not chunk.text.startswith(" ") for chunk in first)
    assert all(not chunk.text.endswith(" ") for chunk in first)
    for chunk in first:
        metadata = chunk.metadata
        assert source.content[metadata.char_start : metadata.char_end] == (
            chunk.text
        )
        assert metadata.content_hash == hashlib.sha256(
            chunk.text.encode("utf-8")
        ).hexdigest()
        assert chunk.source_id == source.source_id
        assert chunk.source_url == source.source_url
        assert metadata.section == "findings"
        assert metadata.location == "body"
    for left, right in zip(first, first[1:]):
        assert set(left.text.split()) & set(right.text.split())


def test_chunk_id_changes_with_source_provenance() -> None:
    content = "A compact source passage that remains identical between URLs."
    chunker = DocumentChunker(chunk_size=100, overlap=10)
    left = chunker.chunk(_source("source-001", content))[0]
    right = chunker.chunk(
        _source(
            "source-001",
            content,
            url="https://different.example/report",
        )
    )[0]

    assert left.metadata.content_hash == right.metadata.content_hash
    assert left.chunk_id != right.chunk_id


def test_mock_embeddings_are_deterministic_and_dimensionally_consistent() -> None:
    provider = MockEmbeddingProvider("configured-mock-model", dimensions=32)

    vectors = asyncio.run(
        provider.embed_texts(
            ["solar energy storage", "solar energy storage", "marine biology"]
        )
    )

    assert vectors[0] == vectors[1]
    assert len(vectors[0]) == len(vectors[2]) == 32
    assert provider.vector_dimension == 32
    assert cosine_similarity(vectors[0], vectors[1]) == pytest.approx(1.0)
    assert cosine_similarity(vectors[0], vectors[2]) < 1.0


def test_cosine_similarity_known_values_and_validation() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    with pytest.raises(ValueError, match="equal dimensions"):
        cosine_similarity([1.0], [1.0, 0.0])


class _FakeEmbeddingModels:
    async def embed_content(
        self,
        *,
        model: str,
        contents: list[str],
    ) -> SimpleNamespace:
        assert model == "configured-gemini-embedding"
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[float(index), 1.0, 2.0])
                for index, _ in enumerate(contents, start=1)
            ]
        )


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.models = _FakeEmbeddingModels()

    async def aclose(self) -> None:
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.aio = _FakeAsyncClient()


def test_gemini_embeddings_use_configured_model_without_live_call() -> None:
    provider = GeminiEmbeddingProvider(
        model_name="configured-gemini-embedding",
        api_key=None,
        client=_FakeClient(),
    )

    vectors = asyncio.run(provider.embed_texts(["tiny one", "tiny two"]))

    assert len(vectors) == 2
    assert all(len(vector) == 3 for vector in vectors)
    assert provider.vector_dimension == 3


def test_index_duplicate_prevention_retrieval_ranking_and_filtering() -> None:
    provider = MockEmbeddingProvider(dimensions=64)
    store = InMemoryVectorStore()
    indexing = RAGIndexingService(
        provider,
        store,
        chunk_size=200,
        chunk_overlap=20,
    )
    retrieval = RAGRetrievalService(provider, store)
    request = IndexRequest(
        sources=[
            _source(
                "source-001",
                "Solar energy storage uses batteries for later electricity.",
            ),
            _source(
                "source-002",
                "Marine biology examines organisms living in ocean habitats.",
            ),
        ]
    )

    first = asyncio.run(indexing.index(request))
    duplicate = asyncio.run(indexing.index(request))
    ranked = asyncio.run(
        retrieval.retrieve(
            RetrievalRequest(query="solar energy battery storage", top_k=2)
        )
    )
    filtered = asyncio.run(
        retrieval.retrieve(
            RetrievalRequest(
                query="solar energy battery storage",
                top_k=2,
                source_ids=["source-002"],
            )
        )
    )

    assert first.sources_indexed == 2
    assert first.chunks_created == 2
    assert first.failures == 0
    assert duplicate.sources_indexed == 0
    assert duplicate.chunks_created == 0
    assert duplicate.duplicates_skipped == 2
    assert ranked[0].source_id == "source-001"
    assert filtered and {item.source_id for item in filtered} == {
        "source-002"
    }
    assert ranked[0].source_url == request.sources[0].source_url
    assert ranked[0].metadata.content_hash == hashlib.sha256(
        ranked[0].text.encode("utf-8")
    ).hexdigest()


def test_vector_store_deletion_clear_and_empty_search() -> None:
    async def exercise() -> None:
        provider = MockEmbeddingProvider(dimensions=16)
        store = InMemoryVectorStore()
        retrieval = RAGRetrievalService(provider, store)
        empty = await retrieval.retrieve(
            RetrievalRequest(query="nothing indexed", top_k=3)
        )
        assert empty == []

        indexing = RAGIndexingService(
            provider,
            store,
            chunk_size=100,
            chunk_overlap=10,
        )
        await indexing.index(
            IndexRequest(
                sources=[
                    _source("source-001", "First indexed source content."),
                    _source("source-002", "Second indexed source content."),
                ]
            )
        )
        assert await store.count() == 2
        assert await store.delete_by_source("source-001") == 1
        assert await store.count() == 1
        assert await store.clear() == 1
        assert await store.count() == 0

    asyncio.run(exercise())


def test_rag_request_validation_rejects_malformed_payloads() -> None:
    with pytest.raises(ValidationError):
        IndexRequest(sources=[])
    with pytest.raises(ValidationError):
        IndexRequest(
            sources=[_source("source-001", "valid source content")],
            chunk_size=64,
            chunk_overlap=64,
        )
    with pytest.raises(ValidationError):
        RetrievalRequest(query=" ", top_k=1)
    with pytest.raises(ValidationError):
        RetrievalRequest(query="valid query", top_k=0)


def test_rag_api_index_search_and_stats() -> None:
    async def exercise() -> None:
        store = get_vector_store()
        await store.clear()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            index_response = await client.post(
                "/api/v1/rag/index",
                json={
                    "sources": [
                        {
                            "source_id": "source-077",
                            "source_url": "https://api.example/source",
                            "title": "API source",
                            "content": (
                                "Semantic retrieval keeps grounded source "
                                "content and provenance together."
                            ),
                        }
                    ],
                    "chunk_size": 100,
                    "chunk_overlap": 10,
                },
            )
            search_response = await client.post(
                "/api/v1/rag/search",
                json={
                    "query": "semantic retrieval provenance",
                    "top_k": 3,
                    "source_ids": ["source-077"],
                },
            )
            stats_response = await client.get("/api/v1/rag/stats")
            malformed_response = await client.post(
                "/api/v1/rag/search",
                json={"query": "", "top_k": 0},
            )

        assert index_response.status_code == 200
        assert index_response.json()["chunks_created"] == 1
        assert search_response.status_code == 200
        result = search_response.json()[0]
        assert result["source_id"] == "source-077"
        assert result["source_url"] == "https://api.example/source"
        assert stats_response.status_code == 200
        assert stats_response.json()["vector_count"] == 1
        assert stats_response.json()["embedding_provider"] == "mock"
        assert malformed_response.status_code == 422
        await store.clear()

    asyncio.run(exercise())
