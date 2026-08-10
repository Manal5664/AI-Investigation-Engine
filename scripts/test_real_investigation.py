import asyncio
import sys

from app.core.config import settings
from app.evidence.gemini_extractor import GeminiEvidenceExtractor
from app.research.search.gemini_grounded_provider import (
    GeminiGroundedSearchProvider,
)
from app.schemas.research import InvestigationResearchRequest
from app.services.investigation_research_service import (
    InvestigationResearchService,
)


async def main() -> int:
    if settings.GEMINI_API_KEY is None:
        print(
            "GEMINI_API_KEY is not set; real investigation test skipped."
        )
        return 0

    search_provider = GeminiGroundedSearchProvider(
        model_name=settings.SEARCH_MODEL,
        api_key=settings.GEMINI_API_KEY,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
    evidence_extractor = GeminiEvidenceExtractor(
        model_name=settings.EVIDENCE_MODEL,
        api_key=settings.GEMINI_API_KEY,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
    try:
        result = await InvestigationResearchService(
            search_provider=search_provider,
            evidence_extractor=evidence_extractor,
        ).research(
            InvestigationResearchRequest(
                query=(
                    "What official evidence describes recent progress in "
                    "long-duration energy storage?"
                ),
                depth="quick",
                max_sub_questions=1,
                max_sources_per_question=2,
            )
        )
    finally:
        await evidence_extractor.aclose()
        await search_provider.aclose()

    print(f"Status: {result.status}")
    print("\nPlan:")
    print(f"- Query: {result.plan.query}")
    print(f"- Depth: {result.plan.depth.value}")
    for question in result.plan.sub_questions:
        print(f"- {question.id}: {question.question}")

    for question_result in result.question_results:
        print(f"\nSelected question: {question_result.sub_question.question}")
        print("Sources:")
        for source in question_result.sources:
            print(f"- {source.source_id} | {source.title} | {source.url}")

        print("Evidence:")
        for evidence in question_result.evidence_items:
            print(
                f"- {evidence.evidence_id} | "
                f"source={evidence.provenance.source_id} | "
                f"stance={evidence.stance.value} | "
                f"strength={evidence.strength.value}"
            )
            print(f"  Passage: {evidence.provenance.relevant_passage}")
            print(f"  Rationale: {evidence.rationale}")

        print("Conflicts:")
        if not question_result.conflicts.unresolved_conflicts:
            print("- None detected")
        for conflict in question_result.conflicts.unresolved_conflicts:
            print(f"- {conflict}")

    if result.error is not None:
        print(
            "\nProvider error: "
            f"{result.error.message} "
            f"(retryable={result.error.retryable})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
