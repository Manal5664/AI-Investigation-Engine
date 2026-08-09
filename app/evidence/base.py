from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.schemas.evidence import EvidenceItem
from app.schemas.investigation import InvestigationSubQuestion
from app.schemas.source import Source


class EvidenceExtractor(ABC):
    @abstractmethod
    async def extract(
        self,
        sub_question: InvestigationSubQuestion,
        sources: Sequence[Source],
    ) -> list[EvidenceItem]:
        """Extract evidence only from the supplied normalized sources."""
