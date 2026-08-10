from typing import Annotated

from pydantic import Field, HttpUrl, StringConstraints, model_validator

from app.schemas.investigation import StrictModel


NonEmptyText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1),
]


class IndexSource(StrictModel):
    """Normalized source content accepted by the RAG indexing boundary."""

    source_id: NonEmptyText
    source_url: HttpUrl
    title: NonEmptyText
    content: NonEmptyText
    section: NonEmptyText | None = None
    location: NonEmptyText | None = None


class ChunkMetadata(StrictModel):
    title: NonEmptyText
    section: NonEmptyText | None = None
    location: NonEmptyText | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_index: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> "ChunkMetadata":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class DocumentChunk(StrictModel):
    chunk_id: str = Field(pattern=r"^chunk-[0-9a-f]{64}$")
    source_id: NonEmptyText
    source_url: HttpUrl
    text: NonEmptyText
    metadata: ChunkMetadata


class IndexRequest(StrictModel):
    sources: list[IndexSource] = Field(min_length=1)
    chunk_size: int | None = Field(default=None, ge=1, le=100_000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=99_999)

    @model_validator(mode="after")
    def validate_chunking(self) -> "IndexRequest":
        if (
            self.chunk_size is not None
            and self.chunk_overlap is not None
            and self.chunk_overlap >= self.chunk_size
        ):
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class IndexResult(StrictModel):
    sources_indexed: int = Field(ge=0)
    chunks_created: int = Field(ge=0)
    duplicates_skipped: int = Field(ge=0)
    failures: int = Field(ge=0)
    failure_details: list[str] = Field(default_factory=list)
    provider_used: NonEmptyText
    model_used: NonEmptyText
    vector_store: NonEmptyText
    vector_dimension: int | None = Field(default=None, gt=0)


class RetrievalRequest(StrictModel):
    query: NonEmptyText
    top_k: int = Field(default=5, ge=1, le=100)
    source_ids: list[NonEmptyText] | None = Field(
        default=None,
        min_length=1,
    )
    source_urls: list[HttpUrl] | None = Field(
        default=None,
        min_length=1,
    )


class RetrievalResult(StrictModel):
    chunk_id: str = Field(pattern=r"^chunk-[0-9a-f]{64}$")
    source_id: NonEmptyText
    source_url: HttpUrl
    text: NonEmptyText
    similarity_score: float = Field(ge=-1.0, le=1.0)
    metadata: ChunkMetadata


class VectorStoreStats(StrictModel):
    store_type: NonEmptyText
    vector_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    vector_dimension: int | None = Field(default=None, gt=0)
    embedding_provider: NonEmptyText | None = None
    embedding_model: NonEmptyText | None = None
