import asyncio
import json
import sys

from app.ai.base import LLMProviderError
from app.ai.gemini_provider import GeminiLLMProvider
from app.core.exceptions import ApplicationConfigurationError
from app.core.config import settings
from app.schemas.investigation import InvestigationDepth


async def main() -> int:
    if settings.GEMINI_API_KEY is None:
        print("GEMINI_API_KEY is not set; Gemini integration test skipped.")
        return 0

    model_name = settings.LLM_MODEL.strip()
    if not model_name or model_name == "mock-investigator":
        print("Set LLM_MODEL to a Gemini model before running this script.")
        return 1

    provider = GeminiLLMProvider(
        model_name=model_name,
        api_key=settings.GEMINI_API_KEY,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
    try:
        try:
            payload = await provider.generate_investigation_plan(
                "Investigate the evidence for long-duration energy storage options",
                InvestigationDepth.QUICK,
            )
        except (ApplicationConfigurationError, LLMProviderError) as exc:
            print(f"Gemini integration test failed: {exc}", file=sys.stderr)
            return 1
    finally:
        await provider.aclose()

    print("Gemini structured investigation plan:\n" + json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
