import asyncio
import json
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.ai.prompts import build_graph_extraction_prompt
from app.core.exceptions import ApplicationConfigurationError
from app.graph.extraction.base import (
    GraphExtractionPayload,
    GraphExtractionProvider,
    GraphExtractionProviderError,
    GraphExtractionResult,
)


class GeminiGraphExtractionProvider(GraphExtractionProvider):
    """Extract grounded entities/relations with Gemini structured output.

    The model receives only the supplied source/evidence content and must
    never emit source IDs, evidence IDs, or URLs. The structured schema rejects
    any such invented field before the result is returned.
    """

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
                "GRAPH_EXTRACTION_MODEL is required when "
                "GRAPH_EXTRACTION_PROVIDER is 'gemini'."
            )
        normalized_api_key = (api_key or "").strip()
        if not normalized_api_key:
            raise ApplicationConfigurationError(
                "GEMINI_API_KEY is required when GRAPH_EXTRACTION_PROVIDER "
                "is 'gemini'."
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

    async def extract_entities_and_relations(
        self,
        *,
        source_id: str,
        source_url: str,
        content: str,
    ) -> GraphExtractionResult:
        normalized_source_id = source_id.strip()
        normalized_source_url = source_url.strip()
        normalized_content = content.strip()
        if not normalized_source_id or not normalized_source_url:
            raise self._grounding_error(
                "Supplied source IDs and URLs must not be empty."
            )
        if not normalized_content:
            raise self._grounding_error(
                "Supplied source content must not be empty."
            )

        prompt = build_graph_extraction_prompt(
            source_id=normalized_source_id,
            source_url=normalized_source_url,
            content=normalized_content,
            include_schema=False,
        )
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=(
                GraphExtractionPayload.model_json_schema()
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
            raise GraphExtractionProviderError(
                "Gemini graph extraction timed out.",
                error_type="timeout",
                provider=self.provider_name,
                model=self.model_name,
                retryable=True,
            ) from exc
        except Exception as exc:
            raise self._provider_error(exc) from exc

        payload = self._parse_payload(response_text)
        return self._validate_and_build_result(
            payload,
            content=normalized_content,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aio.aclose()

    def _parse_payload(self, response_text: Any) -> GraphExtractionPayload:
        if not isinstance(response_text, str) or not response_text.strip():
            raise GraphExtractionProviderError(
                "Gemini graph extraction returned an empty response.",
                error_type="malformed_output",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            )
        try:
            raw_payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise GraphExtractionProviderError(
                "Gemini graph extraction returned malformed JSON.",
                error_type="malformed_output",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            ) from exc
        try:
            return GraphExtractionPayload.model_validate(raw_payload)
        except ValidationError as exc:
            raise GraphExtractionProviderError(
                "Gemini graph output failed schema validation.",
                error_type="malformed_output",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
            ) from exc

    def _validate_and_build_result(
        self,
        payload: GraphExtractionPayload,
        *,
        content: str,
    ) -> GraphExtractionResult:
        seen_names: set[str] = set()
        for entity in payload.entities:
            normalized_name = entity.name.strip()
            if not normalized_name:
                raise self._grounding_error(
                    "Entity names must not be empty."
                )
            if normalized_name.casefold() in seen_names:
                raise self._grounding_error(
                    "Entity names must be unique within one extraction."
                )
            if normalized_name not in content:
                raise self._grounding_error(
                    "An entity name was not present verbatim in the supplied "
                    "content."
                )
            seen_names.add(normalized_name.casefold())

        known_names = {name.casefold() for name in seen_names}
        for relation in payload.relations:
            source = relation.source_name.strip()
            target = relation.target_name.strip()
            if not source or not target:
                raise self._grounding_error(
                    "Relation endpoints must not be empty."
                )
            if source.casefold() not in known_names:
                raise self._grounding_error(
                    "A relation referenced an entity that was not extracted "
                    "from the supplied content."
                )
            if target.casefold() not in known_names:
                raise self._grounding_error(
                    "A relation referenced an entity that was not extracted "
                    "from the supplied content."
                )
            if source.casefold() == target.casefold():
                raise self._grounding_error(
                    "Relations must connect two distinct entities."
                )

        entities = [
            entity.model_copy(update={"name": entity.name.strip()})
            for entity in payload.entities
        ]
        relations = [
            relation.model_copy(
                update={
                    "source_name": relation.source_name.strip(),
                    "target_name": relation.target_name.strip(),
                }
            )
            for relation in payload.relations
        ]
        return GraphExtractionResult(
            provider_used=self.provider_name,
            model_used=self.model_name,
            entities=entities,
            relations=relations,
        )

    def _grounding_error(self, message: str) -> GraphExtractionProviderError:
        return GraphExtractionProviderError(
            message,
            error_type="grounding_validation",
            provider=self.provider_name,
            model=self.model_name,
            retryable=False,
        )

    def _provider_error(self, exc: Exception) -> GraphExtractionProviderError:
        if self._is_rate_limit_error(exc):
            return GraphExtractionProviderError(
                "Gemini graph extraction is temporarily unavailable because "
                "the API quota or rate limit was exhausted.",
                error_type="rate_limit",
                provider=self.provider_name,
                model=self.model_name,
                retryable=True,
                retry_after_seconds=self._retry_after_seconds(exc),
            )
        if isinstance(exc, errors.ClientError):
            message = self._describe_api_error(
                exc,
                prefix="Gemini graph extraction rejected the request",
            )
            retryable = False
            error_type = "provider_request"
        elif isinstance(exc, errors.ServerError):
            message = self._describe_api_error(
                exc,
                prefix="Gemini graph extraction service error",
            )
            retryable = True
            error_type = "provider_unavailable"
        else:
            message = (
                "Gemini graph extraction failed "
                f"({type(exc).__name__})."
            )
            retryable = False
            error_type = "provider_error"
        return GraphExtractionProviderError(
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
