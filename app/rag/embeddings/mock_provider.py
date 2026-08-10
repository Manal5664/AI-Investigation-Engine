import asyncio
import hashlib
import math
import re
from collections.abc import Sequence

from app.rag.embeddings.base import EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic token-hashing embeddings for offline development."""

    def __init__(
        self,
        model_name: str = "mock-embedding-v1",
        *,
        dimensions: int = 64,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        if dimensions <= 0:
            raise ValueError("dimensions must be greater than zero")
        self._model_name = model_name.strip()
        self._dimensions = dimensions

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def vector_dimension(self) -> int:
        return self._dimensions

    async def embed_text(self, text: str) -> list[float]:
        values = await self.embed_texts([text])
        return values[0]

    async def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        await asyncio.sleep(0)
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        normalized = text.strip().casefold()
        if not normalized:
            raise ValueError("Embedding text must not be empty")
        tokens = re.findall(r"[w]+", normalized, flags=re.UNICODE)
        if not tokens:
            tokens = [normalized]

        features = [(token, 1.0) for token in tokens]
        features.extend(
            (f"{left}::{right}", 0.5)
            for left, right in zip(tokens, tokens[1:])
        )
        vector = [0.0] * self._dimensions
        for feature, weight in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * weight

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            vector[0] = 1.0
            magnitude = 1.0
        return [value / magnitude for value in vector]
