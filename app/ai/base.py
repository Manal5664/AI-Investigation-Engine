from abc import ABC, abstractmethod
from typing import Any

from app.schemas.investigation import InvestigationDepth


class LLMProviderError(Exception):
    """Base error raised by provider adapters for generation failures."""


class LLMProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable provider identifier."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the configured model identifier."""

    @abstractmethod
    async def generate_investigation_plan(
        self,
        query: str,
        depth: InvestigationDepth,
    ) -> dict[str, Any]:
        """Generate a JSON-compatible structured investigation plan."""
