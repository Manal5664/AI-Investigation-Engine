import asyncio
import hashlib
import json
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.ai.prompts import build_evidence_extraction_prompt
from app.core.exceptions import ApplicationConfigurationError
from app.evidence.base import EvidenceExtractor, EvidenceProviderError
from app.schemas.evidence import (
    EvidenceExtractionPayload,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceStance,
    EvidenceStrength,
)
from app.schemas.investigation import InvestigationSubQuestion
from app.schemas.source import Source


class GeminiEvidenceExtractor(EvidenceExtractor):
    """Extract source-bound evidence with Gemini structured output."""

    def __init__(
        self,
        *,
        model_name: str,
        api_key: str | None,
        timeout_seconds: int = 60,
        client: Any | None = None,
    ) -> None:
        normalized_model = model_name.strip()
        if not normalized_model:
            raise ApplicationConfigurationError(
                "EVIDENCE_MODEL is required when EVIDENCE_PROVIDER is "
                "'gemini'."
            )
        normalized_api_key = (api_key or "").strip()
        if not normalized_api_key:
            raise ApplicationConfigurationError(
                "GEMINI_API_KEY is required when EVIDENCE_PROVIDER is "
                "'gemini'."
            )
        if timeout_seconds <= 0:
            raise ApplicationConfigurationError(
                "LLM_TIMEOUT_SECONDS must be greater than zero."
            )

        self._model_name = normalized_model
        self._timeout_seconds = timeout_seconds
        self._api_key_for_redaction = normalized_api_key
        self._owns_client = client is None
        self._client = client or genai.Client(api_key=normalized_api_key)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def extract(
        self,
        sub_question: InvestigationSubQuestion,
        sources: Sequence[Source],
        *,
        investigation_query: str | None = None,
    ) -> list[EvidenceItem]:
        if not sources:
            return []

        known_sources = self._index_sources(sources)
        query = (investigation_query or sub_question.question).strip()
        prompt = build_evidence_extraction_prompt(
            query,
            sub_question.question,
            sources,
            include_schema=False,
        )
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=(
                EvidenceExtractionPayload.model_json_schema()
            ),
            temperature=0.0,
        )

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                    config=config,
                ),
                timeout=self._timeout_seconds,
            )
            response_text = response.text
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise EvidenceProviderError(
                "Gemini evidence extraction timed out.",
                error_type="timeout",
                provider=self.provider_name,
                model=self.model_name,
                retryable=True,
            ) from exc
        except Exception as exc:
            raise self._provider_error(exc) from exc

        payload = self._parse_payload(response_text)
        return self._validate_and_build_items(
            payload,
            sub_question,
            known_sources,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aio.aclose()

    def _parse_payload(self, response_text: Any) -> EvidenceExtractionPayload:
        if not isinstance(response_text, str) or not response_text.strip():
            raise EvidenceProviderError(
                "Gemini evidence extraction returned an empty response.",
                error_type="malformed_output",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            )
        try:
            raw_payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise EvidenceProviderError(
                "Gemini evidence extraction returned malformed JSON.",
                error_type="malformed_output",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            ) from exc
        try:
            return EvidenceExtractionPayload.model_validate(raw_payload)
        except ValidationError as exc:
            raise EvidenceProviderError(
                "Gemini evidence output failed schema validation.",
                error_type="malformed_output",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            ) from exc

    def _validate_and_build_items(
        self,
        payload: EvidenceExtractionPayload,
        sub_question: InvestigationSubQuestion,
        known_sources: dict[str, Source],
    ) -> list[EvidenceItem]:
        seen_source_ids: set[str] = set()
        items: list[EvidenceItem] = []
        for index, candidate in enumerate(payload.evidence_items, start=1):
            source = known_sources.get(candidate.source_id)
            if source is None:
                raise self._grounding_error(
                    "Evidence output referenced an unknown source ID."
                )
            if candidate.source_id in seen_source_ids:
                raise self._grounding_error(
                    "Evidence output referenced a supplied source more than "
                    "once."
                )
            if str(candidate.source_url) != str(source.url):
                raise self._grounding_error(
                    "Evidence output changed a supplied source URL."
                )

            source_material = source.snippet or source.title
            passage = candidate.relevant_passage
            if passage not in source_material:
                raise self._grounding_error(
                    "Evidence output contained a passage that was not present "
                    "verbatim in the supplied source material."
                )
            if (
                candidate.stance is EvidenceStance.INSUFFICIENT
                and candidate.strength is not EvidenceStrength.UNKNOWN
            ):
                raise self._grounding_error(
                    "Insufficient evidence must use unknown strength."
                )

            seen_source_ids.add(candidate.source_id)
            items.append(
                EvidenceItem(
                    evidence_id=f"evidence-{index:03d}",
                    sub_question_id=sub_question.id,
                    summary=candidate.rationale,
                    rationale=candidate.rationale,
                    stance=candidate.stance,
                    strength=candidate.strength,
                    provenance=EvidenceProvenance(
                        source_id=source.source_id,
                        source_url=source.url,
                        relevant_passage=passage,
                        retrieved_at=source.retrieved_at,
                        extraction_method="gemini_structured_source_extraction",
                        model_used=self.model_name,
                        content_hash=hashlib.sha256(
                            passage.encode("utf-8")
                        ).hexdigest(),
                        location=(
                            "source.snippet"
                            if source.snippet is not None
                            else "source.title"
                        ),
                    ),
                )
            )

        missing_source_ids = set(known_sources) - seen_source_ids
        if missing_source_ids:
            raise self._grounding_error(
                "Evidence output omitted one or more supplied sources."
            )
        return items

    def _index_sources(
        self,
        sources: Sequence[Source],
    ) -> dict[str, Source]:
        indexed: dict[str, Source] = {}
        urls: set[str] = set()
        for source in sources:
            source_url = str(source.url)
            if source.source_id in indexed or source_url in urls:
                raise self._grounding_error(
                    "Supplied sources must have unique IDs and URLs."
                )
            indexed[source.source_id] = source
            urls.add(source_url)
        return indexed

    def _grounding_error(self, message: str) -> EvidenceProviderError:
        return EvidenceProviderError(
            message,
            error_type="grounding_validation",
            provider=self.provider_name,
            model=self.model_name,
            retryable=False,
        )

    def _provider_error(self, exc: Exception) -> EvidenceProviderError:
        if self._is_rate_limit_error(exc):
            return EvidenceProviderError(
                "Gemini evidence extraction is temporarily unavailable "
                "because the API quota or rate limit was exhausted.",
                error_type="rate_limit",
                provider=self.provider_name,
                model=self.model_name,
                retryable=True,
                retry_after_seconds=self._retry_after_seconds(exc),
            )
        if isinstance(exc, errors.ClientError):
            message = self._describe_api_error(
                exc,
                prefix="Gemini evidence extraction rejected the request",
            )
            retryable = False
            error_type = "provider_request"
        elif isinstance(exc, errors.ServerError):
            message = self._describe_api_error(
                exc,
                prefix="Gemini evidence extraction service error",
            )
            retryable = True
            error_type = "provider_unavailable"
        else:
            message = (
                "Gemini evidence extraction failed "
                f"({type(exc).__name__})."
            )
            retryable = False
            error_type = "provider_error"
        return EvidenceProviderError(
            message,
            error_type=error_type,
            provider=self.provider_name,
            model=self.model_name,
            retryable=retryable,
        )

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        response = getattr(exc, "response", None)
        values = (
            getattr(exc, "status_code", None),
            getattr(exc, "code", None),
            getattr(exc, "status", None),
            getattr(response, "status_code", None),
        )
        if any(
            str(value).strip().casefold()
            in {"429", "resource_exhausted"}
            for value in values
            if value is not None
        ):
            return True
        name = type(exc).__name__.casefold().replace("_", "")
        return name in {"ratelimiterror", "resourceexhausted"}

    @staticmethod
    def _retry_after_seconds(exc: Exception) -> float | None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        value = headers.get("retry-after")
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return None
        return seconds if seconds >= 0 else None

    def _describe_api_error(
        self,
        exc: errors.APIError,
        *,
        prefix: str,
    ) -> str:
        code = getattr(exc, "code", None)
        status = getattr(exc, "status", None)
        raw_message = str(getattr(exc, "message", "") or "")
        safe_message = raw_message.replace(
            self._api_key_for_redaction,
            "[redacted]",
        )
        safe_message = " ".join(safe_message.split())[:500]
        metadata = ", ".join(
            item
            for item in (
                f"code={code}" if code is not None else "",
                f"status={status}" if status else "",
            )
            if item
        )
        description = f" ({metadata})" if metadata else ""
        detail = f": {safe_message}" if safe_message else "."
        return f"{prefix}{description}{detail}"
