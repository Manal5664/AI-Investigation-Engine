import asyncio
import sys

from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.research.search.base import SearchProviderRateLimitError
from app.research.search.gemini_grounded_provider import (
    GeminiGroundedSearchProvider,
)
from app.services.web_research_service import WebResearchService


async def main() -> int:
    if settings.GEMINI_API_KEY is None:
        print(
            "GEMINI_API_KEY is not set; grounded web research test skipped."
        )
        return 0

    provider = GeminiGroundedSearchProvider(
        model_name=settings.SEARCH_MODEL,
        api_key=settings.GEMINI_API_KEY,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
    try:
        try:
            result = await WebResearchService(provider).research(
                "What are the latest official developments in long-duration "
                "energy storage?",
                max_results=min(settings.SEARCH_MAX_RESULTS, 3),
            )
        except SearchProviderRateLimitError as exc:
            retry_guidance = (
                f" Retry after approximately "
                f"{exc.retry_after_seconds:g} seconds."
                if exc.retry_after_seconds is not None
                else " Try again after the Gemini API quota is available."
            )
            print(
                "Grounded web research is unavailable: the Gemini API "
                "quota/rate limit is currently exhausted."
                f"{retry_guidance} No mock sources were substituted.",
                file=sys.stderr,
            )
            return 1
        except ApplicationError as exc:
            print(
                f"Grounded web research test failed: {exc.message}",
                file=sys.stderr,
            )
            return 1
    finally:
        await provider.aclose()

    print("Grounded summary:")
    print(result.grounded_summary or "(No grounded summary returned)")
    print("\nGrounded sources:")
    if not result.sources:
        print("(No usable grounded source metadata returned)")
    for source in result.sources:
        print(f"- {source.title}: {source.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
