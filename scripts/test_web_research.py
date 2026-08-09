import asyncio
import sys

from app.core.config import settings
from app.core.exceptions import ApplicationError
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
