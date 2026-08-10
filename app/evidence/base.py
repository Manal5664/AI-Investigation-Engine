from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.core.exceptions import ApplicationError
from app.schemas.evidence import EvidenceItem
from app.schemas.investigation import InvestigationSubQuestion
from app.schemas.source import Source


class EvidenceProviderError(ApplicationError):
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
            code="evidence_provider_error",
            status_code=502,
        )
        self.error_type = error_type
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class EvidenceExtractor(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable evidence-provider identifier."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the configured extraction model identifier."""

    @abstractmethod
    async def extract(
        self,
        sub_question: InvestigationSubQuestion,
        sources: Sequence[Source],
        *,
        investigation_query: str | None = None,
    ) -> list[EvidenceItem]:
        """Extract evidence only from the supplied normalized sources."""

    async def aclose(self) -> None:
        """Release provider resources when the adapter owns any."""
