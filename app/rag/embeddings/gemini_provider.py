import asyncio
import math
from collections.abc import Sequence
from typing import Any

from google import genai

from app.core.exceptions import ApplicationConfigurationError
from app.rag.embeddings.base import (
    EmbeddingProvider,
    EmbeddingProviderError,
)


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gen AI embedding adapter using the configured model."""

    def __init__(
        self,
        *,
        model_name: str,
        api_key: str | None,
        timeout_seconds: int = 60,
        client: Any | None = None,
    ) -> None:
        if not model_name.strip():
            raise ApplicationConfigurationError(
                "EMBEDDING_MODEL must not be empty."
            )
        if timeout_seconds <= 0:
            raise ApplicationConfigurationError(
                "Embedding timeout must be greater than zero."
            )
        if client is None and not api_key:
            raise ApplicationConfigurationError(
                "GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini."
            )
        self._model_name = model_name.strip()
        self._timeout_seconds = timeout_seconds
        self._client = client or genai.Client(api_key=api_key)
        self._owns_client = client is None
        self._vector_dimension: int | None = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def vector_dimension(self) -> int | None:
        return self._vector_dimension

    async def embed_text(self, text: str) -> list[float]:
        values = await self.embed_texts([text])
        return values[0]

    async def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        normalized = [text.strip() for text in texts]
        if any(not text for text in normalized):
            raise ValueError("Embedding text must not be empty")
        if not normalized:
            return []

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.embed_content(
                    model=self._model_name,
                    contents=normalized,
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise EmbeddingProviderError(
                "Gemini embedding generation timed out.",
                provider=self.provider_name,
                model=self.model_name,
                retryable=True,
            ) from exc
        except Exception as exc:
            raise EmbeddingProviderError(
                "Gemini embedding generation failed "
                f"({type(exc).__name__}).",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            ) from exc

        embeddings = getattr(response, "embeddings", None)
        if embeddings is None or len(embeddings) != len(normalized):
            raise EmbeddingProviderError(
                "Gemini returned an unexpected embedding count.",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            )

        vectors: list[list[float]] = []
        for embedding in embeddings:
            raw_values = getattr(embedding, "values", None)
            if not raw_values:
                raise EmbeddingProviderError(
                    "Gemini returned an empty embedding vector.",
                    provider=self.provider_name,
                    model=self.model_name,
                    retryable=False,
                )
            vector = [float(value) for value in raw_values]
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingProviderError(
                    "Gemini returned a non-finite embedding value.",
                    provider=self.provider_name,
                    model=self.model_name,
                    retryable=False,
                )
            if vectors and len(vector) != len(vectors[0]):
                raise EmbeddingProviderError(
                    "Gemini returned inconsistent embedding dimensions.",
                    provider=self.provider_name,
                    model=self.model_name,
                    retryable=False,
                )
            vectors.append(vector)

        dimension = len(vectors[0])
        if (
            self._vector_dimension is not None
            and self._vector_dimension != dimension
        ):
            raise EmbeddingProviderError(
                "Gemini embedding dimension changed during this session.",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            )
        self._vector_dimension = dimension
        return vectors

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aio.aclose()
