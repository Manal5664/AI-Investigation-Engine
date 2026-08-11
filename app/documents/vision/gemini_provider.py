"""Google Gemini vision provider for image-based document reading."""

import asyncio
from typing import Any

from google import genai
from google.genai import errors, types

from app.core.exceptions import ApplicationConfigurationError
from app.documents.models import ExtractedImageContent
from app.documents.vision.base import VisionProvider, VisionProviderError

DESCRIBE_IMAGE_PROMPT = (
    "You are a document examiner. Analyze the provided image and return "
    "JSON with exactly three fields: 'description' (a thorough description "
    "of the document contents), 'visible_text' (every visible string of "
    "text, verbatim, or null if none is readable), and 'objects' (a list "
    "of recognized objects or entities, or an empty list)."
)


class GeminiVisionProvider(VisionProvider):
    """Google Gemini adapter for reading documents from images."""

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
                "VISION_MODEL is required when VISION_PROVIDER is 'gemini'."
            )

        normalized_api_key = (api_key or "").strip()
        if not normalized_api_key:
            raise ApplicationConfigurationError(
                "GEMINI_API_KEY is required when VISION_PROVIDER is 'gemini'."
            )

        if timeout_seconds <= 0:
            raise ApplicationConfigurationError(
                "VISION_TIMEOUT_SECONDS must be greater than zero."
            )

        self._model_name = normalized_model
        self._timeout_seconds = timeout_seconds
        self._api_key_for_redaction = normalized_api_key
        self._owns_client = client is None
        self._client = client or genai.Client(api_key=normalized_api_key)

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def describe(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> ExtractedImageContent:
        inline_data = types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type,
        )
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        )

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model_name,
                    contents=[DESCRIBE_IMAGE_PROMPT, inline_data],
                    config=config,
                ),
                timeout=self._timeout_seconds,
            )
            response_text = response.text
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise VisionProviderError(
                "Gemini vision provider request timed out."
            ) from exc
        except errors.ClientError as exc:
            raise VisionProviderError(
                self._describe_api_error(
                    exc,
                    prefix="Gemini vision provider rejected the request",
                )
            ) from exc
        except errors.ServerError as exc:
            raise VisionProviderError(
                self._describe_api_error(
                    exc,
                    prefix="Gemini vision provider service error",
                )
            ) from exc
        except Exception as exc:
            raise VisionProviderError(
                "Gemini vision provider request failed "
                f"({type(exc).__name__})."
            ) from exc

        if not isinstance(response_text, str) or not response_text.strip():
            raise VisionProviderError(
                "Gemini vision provider returned an empty response."
            )

        try:
            payload = __import__("json").loads(response_text)
            return ExtractedImageContent.model_validate(
                {
                    "description": payload.get(
                        "description",
                        f"Description of '{filename}'.",
                    ),
                    "visible_text": payload.get("visible_text"),
                    "objects": payload.get("objects", []),
                    "provider_used": "gemini",
                    "model_used": self._model_name,
                }
            )
        except Exception as exc:
            raise VisionProviderError(
                "Gemini vision provider output failed schema validation."
            ) from exc

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


__all__ = ["GeminiVisionProvider"]
