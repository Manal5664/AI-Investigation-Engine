from collections.abc import Sequence
from dataclasses import dataclass

from app.evidence.base import EvidenceExtractor, EvidenceProviderError
from app.schemas.evidence import EvidenceItem
from app.schemas.investigation import InvestigationSubQuestion
from app.schemas.source import Source


@dataclass(frozen=True, slots=True)
class EvidenceSourceFailure:
    source_id: str
    error: EvidenceProviderError


@dataclass(frozen=True, slots=True)
class EvidenceAgentResult:
    evidence_items: list[EvidenceItem]
    warnings: list[str]
    failures: list[EvidenceSourceFailure]


class EvidenceAgent:
    """Extract and independently validate evidence one source at a time."""

    MAX_SOURCES_PER_QUESTION = 3

    def __init__(self, extractor: EvidenceExtractor) -> None:
        self._extractor = extractor

    @property
    def provider_name(self) -> str:
        return self._extractor.provider_name

    @property
    def model_name(self) -> str:
        return self._extractor.model_name

    async def extract(
        self,
        investigation_query: str,
        sub_question: InvestigationSubQuestion,
        sources: Sequence[Source],
        *,
        evidence_id_start: int = 1,
    ) -> EvidenceAgentResult:
        if len(sources) > self.MAX_SOURCES_PER_QUESTION:
            raise ValueError(
                "Agentic evidence extraction accepts at most 3 sources."
            )

        evidence_items: list[EvidenceItem] = []
        warnings: list[str] = []
        failures: list[EvidenceSourceFailure] = []
        for source in sources:
            try:
                extracted = await self._extractor.extract(
                    sub_question,
                    [source],
                    investigation_query=investigation_query,
                )
                if len(extracted) != 1:
                    raise self._grounding_error(
                        "Evidence extractor must return exactly one item for "
                        "each supplied source."
                    )
                self._validate_item(extracted[0], source)
            except EvidenceProviderError as exc:
                failures.append(
                    EvidenceSourceFailure(
                        source_id=source.source_id,
                        error=exc,
                    )
                )
                warnings.append(
                    f"Evidence extraction failed for {source.source_id}; "
                    "other supplied sources were retained."
                )
                continue

            next_id = evidence_id_start + len(evidence_items)
            evidence_items.append(
                extracted[0].model_copy(
                    update={"evidence_id": f"evidence-{next_id:03d}"}
                )
            )

        return EvidenceAgentResult(
            evidence_items=evidence_items,
            warnings=warnings,
            failures=failures,
        )

    def _validate_item(
        self,
        item: EvidenceItem,
        source: Source,
    ) -> None:
        if item.provenance.source_id != source.source_id:
            raise self._grounding_error(
                "Evidence item referenced an unsupported source ID."
            )
        if str(item.provenance.source_url) != str(source.url):
            raise self._grounding_error(
                "Evidence item referenced an unsupported source URL."
            )
        source_material = source.snippet or source.title
        if item.provenance.relevant_passage not in source_material:
            raise self._grounding_error(
                "Evidence item passage was not present verbatim in the "
                "supplied source material."
            )

    def _grounding_error(self, message: str) -> EvidenceProviderError:
        return EvidenceProviderError(
            message,
            error_type="grounding_validation",
            provider=self.provider_name,
            model=self.model_name,
            retryable=False,
        )
