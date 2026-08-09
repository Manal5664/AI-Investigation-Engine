import asyncio
import json
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.ai.base import LLMProvider, LLMProviderError
from app.ai.prompts import build_investigation_planning_prompt
from app.core.exceptions import ApplicationConfigurationError
from app.schemas.investigation import AIInvestigationPlan, InvestigationDepth


class GeminiLLMProvider(LLMProvider):
    """Google Gemini adapter for structured investigation-plan generation."""

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
                "LLM_MODEL is required when LLM_PROVIDER is 'gemini'."
            )

        normalized_api_key = (api_key or "").strip()
        if not normalized_api_key:
            raise ApplicationConfigurationError(
                "GEMINI_API_KEY is required when LLM_PROVIDER is 'gemini'."
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

    async def generate_investigation_plan(
        self,
        query: str,
        depth: InvestigationDepth,
    ) -> dict[str, Any]:
        prompt = build_investigation_planning_prompt(
            query,
            depth,
            include_schema=False,
        )
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=AIInvestigationPlan.model_json_schema(),
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
            raise LLMProviderError(
                "Gemini provider request timed out."
            ) from exc
        except errors.ClientError as exc:
            raise LLMProviderError(
                self._describe_api_error(
                    exc,
                    prefix="Gemini provider rejected the request",
                )
            ) from exc
        except errors.ServerError as exc:
            raise LLMProviderError(
                self._describe_api_error(
                    exc,
                    prefix="Gemini provider service error",
                )
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                "Gemini provider request failed "
                f"({type(exc).__name__})."
            ) from exc

        if not isinstance(response_text, str) or not response_text.strip():
            raise LLMProviderError(
                "Gemini provider returned an empty structured response."
            )

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                "Gemini provider returned malformed JSON."
            ) from exc

        try:
            plan = AIInvestigationPlan.model_validate(payload)
        except ValidationError as exc:
            raise LLMProviderError(
                "Gemini provider output failed AIInvestigationPlan "
                "schema validation."
            ) from exc

        return plan.model_dump(mode="json")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aio.aclose()

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
