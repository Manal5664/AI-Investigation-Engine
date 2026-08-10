from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.core.exceptions import ApplicationError


class EmbeddingProviderError(ApplicationError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        retryable: bool,
    ) -> None:
        super().__init__(
            message,
            code="embedding_provider_error",
            status_code=502,
        )
        self.provider = provider
        self.model = model
        self.retryable = retryable


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable provider identifier."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the configured embedding model identifier."""

    @property
    @abstractmethod
    def vector_dimension(self) -> int | None:
        """Return the known output dimension, if an embedding has been made."""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Embed one non-empty text value."""

    @abstractmethod
    async def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """Embed a batch while preserving input order."""

    async def aclose(self) -> None:
        """Release provider resources when the adapter owns any."""
