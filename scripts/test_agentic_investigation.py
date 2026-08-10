import asyncio
import sys

from app.agents.critic_agent import CriticAgent
from app.agents.evidence_agent import EvidenceAgent
from app.agents.orchestrator import InvestigationOrchestrator
from app.agents.research_agent import ResearchAgent
from app.core.config import settings
from app.evidence.gemini_extractor import GeminiEvidenceExtractor
from app.research.search.gemini_grounded_provider import (
    GeminiGroundedSearchProvider,
)
from app.schemas.agentic import AgenticInvestigationRequest


async def main() -> int:
    if settings.GEMINI_API_KEY is None:
        print(
            "GEMINI_API_KEY is not set; agentic investigation test skipped."
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
    research_agent = ResearchAgent(search_provider)
    evidence_agent = EvidenceAgent(evidence_extractor)
    orchestrator = InvestigationOrchestrator(
        research_agent=research_agent,
        evidence_agent=evidence_agent,
        critic_agent=CriticAgent(
            research_agent=research_agent,
            evidence_agent=evidence_agent,
        ),
    )
    try:
        result = await orchestrator.investigate(
            AgenticInvestigationRequest(
                query=(
                    "What official evidence describes recent progress in "
                    "long-duration energy storage?"
                ),
                depth="quick",
                max_sub_questions=1,
                max_sources_per_question=2,
                run_critic=True,
                max_critic_rounds=1,
            )
        )
    finally:
        await evidence_extractor.aclose()
        await search_provider.aclose()

    state = result.state
    print(f"Status: {result.status}")
    print("\nInvestigation plan:")
    print(f"- Query: {state.plan.query}")
    print(f"- Depth: {state.plan.depth.value}")
    for question in state.selected_sub_questions:
        print(f"- {question.id}: {question.question}")

    print("\nSources and evidence:")
    for question_result in state.question_results:
        print(f"- Question: {question_result.sub_question.question}")
        for source in question_result.research.sources:
            print(f"  Source: {source.source_id} | {source.title} | {source.url}")
        for evidence in question_result.evidence_items:
            print(
                f"  Evidence: {evidence.evidence_id} | "
                f"source={evidence.provenance.source_id} | "
                f"stance={evidence.stance.value} | "
                f"strength={evidence.strength.value}"
            )
            print(f"    Passage: {evidence.provenance.relevant_passage}")

    print("\nCritic findings:")
    print(f"- {state.critic_result.finding_summary}")
    for question in state.critic_result.counter_questions:
        print(f"- Counter-question: {question.question}")
    for assumption in state.critic_result.assumptions_challenged:
        print(f"- Assumption challenged: {assumption}")
    for evidence in state.critic_result.new_evidence_items:
        print(
            f"- Critic evidence: {evidence.evidence_id} | "
            f"stance={evidence.stance.value} | "
            f"strength={evidence.strength.value}"
        )

    print("\nConflicts:")
    unresolved = [
        conflict
        for report in state.conflicts
        for conflict in report.unresolved_conflicts
    ]
    if not unresolved:
        print("- None detected")
    for conflict in unresolved:
        print(f"- {conflict}")

    print("\nSynthesis:")
    print(f"- {state.synthesis.overall_evidence_picture}")
    print(f"- Confidence: {state.synthesis.confidence_level.value}")
    print(f"- {state.synthesis.confidence_rationale}")
    for limitation in state.synthesis.important_limitations:
        print(f"- Limitation: {limitation}")
    for gap in state.synthesis.evidence_gaps:
        print(f"- Evidence gap: {gap}")

    print("\nAudit/replay steps:")
    for step in state.audit_trail:
        print(
            f"- {step.step_id} | {step.step_name} | {step.status.value} | "
            f"sources={step.source_count} | evidence={step.evidence_count}"
        )
        print(f"  {step.action_summary}")

    if state.errors:
        print("\nProvider/action errors:", file=sys.stderr)
        for error in state.errors:
            print(
                f"- {error.provider}/{error.model}: {error.message}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
