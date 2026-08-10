from abc import ABC, abstractmethod

from pydantic import Field

from app.core.exceptions import ApplicationError
from app.graph.models import (
    GraphNodeType,
    GraphRelationType,
)
from app.schemas.investigation import StrictModel


class GraphExtractionProviderError(ApplicationError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        provider: str,
        model: str,
        retryable: bool,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(
            message,
            code="graph_extraction_provider_error",
            status_code=502,
        )
        self.error_type = error_type
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class ExtractedEntity(StrictModel):
    """An entity detected inside one supplied grounded source."""

    name: str = Field(min_length=1, max_length=512)
    node_type: GraphNodeType
    description: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, str] = Field(default_factory=dict)


class ExtractedRelation(StrictModel):
    """A typed relation between two entities in the same source."""

    source_name: str = Field(min_length=1, max_length=512)
    relation_type: GraphRelationType
    target_name: str = Field(min_length=1, max_length=512)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, str] = Field(default_factory=dict)


class GraphExtractionResult(StrictModel):
    provider_used: str = Field(min_length=1)
    model_used: str = Field(min_length=1)
    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]


class GraphExtractionPayload(StrictModel):
    """Provider response body; deliberately carries no source/evidence IDs."""

    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]


class GraphExtractionProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable graph-extraction provider identifier."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the configured extraction model identifier."""

    @abstractmethod
    async def extract_entities_and_relations(
        self,
        *,
        source_id: str,
        source_url: str,
        content: str,
    ) -> GraphExtractionResult:
        """Extract entities and relations only from the supplied content."""

    async def aclose(self) -> None:
        """Release provider resources when the adapter owns any."""
