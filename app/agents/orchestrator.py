import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from app.agents.critic_agent import CriticAgent
from app.agents.evidence_agent import EvidenceAgent
from app.agents.research_agent import ResearchAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.evidence.base import EvidenceProviderError
from app.research.search.base import (
    SearchProviderError,
    SearchProviderRateLimitError,
)
from app.rag.retriever import (
    build_index_sources,
    grounded_sources_from_results,
)
from app.schemas.agentic import (
    AgenticInvestigationRequest,
    AgenticInvestigationResult,
    AgenticQuestionResult,
    AgentStep,
    AgentStepStatus,
    CriticResult,
    InvestigationState,
)
from app.schemas.evidence import (
    EvidenceConflictReport,
    EvidenceItem,
    EvidenceStance,
    EvidenceStanceCounts,
    ProviderFailure,
)
from app.schemas.graph import (
    GraphBuildRequest,
    GraphRAGRequest,
    GraphRAGResult,
)
from app.schemas.investigation import InvestigationRequest
from app.schemas.rag import IndexRequest, RetrievalRequest, RetrievalResult
from app.schemas.source import Source
from app.services.evidence_conflict_service import EvidenceConflictService
from app.services.graph_builder_service import GraphBuilderService
from app.services.graph_rag_service import GraphRAGService
from app.services.investigation_service import InvestigationPlanner
from app.services.rag_indexing_service import RAGIndexingService
from app.services.rag_retrieval_service import RAGRetrievalService


class InvestigationOrchestrator:
    """Execute a finite, auditable investigation workflow."""

    HARD_MAX_SUB_QUESTIONS = 2
    HARD_MAX_SOURCES_PER_QUESTION = 3
    HARD_MAX_CRITIC_ROUNDS = 2

    def __init__(
        self,
        *,
        research_agent: ResearchAgent,
        evidence_agent: EvidenceAgent,
        critic_agent: CriticAgent,
        synthesis_agent: SynthesisAgent | None = None,
        planner: InvestigationPlanner | None = None,
        conflict_service: EvidenceConflictService | None = None,
        rag_indexing_service: RAGIndexingService | None = None,
        rag_retrieval_service: RAGRetrievalService | None = None,
        graph_builder_service: GraphBuilderService | None = None,
        graph_rag_service: GraphRAGService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._research_agent = research_agent
        self._evidence_agent = evidence_agent
        self._critic_agent = critic_agent
        self._synthesis_agent = synthesis_agent or SynthesisAgent()
        self._planner = planner or InvestigationPlanner()
        self._conflict_service = (
            conflict_service or EvidenceConflictService()
        )
        self._rag_indexing_service = rag_indexing_service
        self._rag_retrieval_service = rag_retrieval_service
        self._graph_builder_service = graph_builder_service
        self._graph_rag_service = graph_rag_service
        self._clock = clock or (lambda: datetime.now(UTC))

    async def investigate(
        self,
        request: AgenticInvestigationRequest | InvestigationRequest,
    ) -> AgenticInvestigationResult:
        if isinstance(request, InvestigationRequest):
            request = AgenticInvestigationRequest(
                query=request.query,
                depth=request.depth,
            )
        self._assert_limits(request)
        uses_rag = request.use_rag or request.use_graph_rag
        if uses_rag and (
            self._rag_indexing_service is None
            or self._rag_retrieval_service is None
        ):
            raise ValueError(
                "RAG services are required when use_rag or use_graph_rag "
                "is true."
            )
        if request.use_graph_rag and (
            self._graph_builder_service is None
            or self._graph_rag_service is None
        ):
            raise ValueError(
                "Graph services are required when use_graph_rag is true."
            )
        audit: list[AgentStep] = []
        warnings = [
            "Agent execution is finite: at most "
            f"{request.max_sub_questions} primary question(s), "
            f"{request.max_sources_per_question} source(s) per question, and "
            f"{request.max_critic_rounds if request.run_critic else 0} "
            "critic round(s)."
        ]
        errors: list[ProviderFailure] = []
        all_sources: list[Source] = []
        all_evidence: list[EvidenceItem] = []
        conflicts: list[EvidenceConflictReport] = []
        question_results: list[AgenticQuestionResult] = []

        plan_started = self._now()
        plan = self._planner.plan(
            InvestigationRequest(query=request.query, depth=request.depth)
        )
        selected_questions = sorted(
            plan.sub_questions,
            key=lambda question: question.priority,
        )[: request.max_sub_questions]
        self._append_step(
            audit,
            step_name="plan_created",
            status=AgentStepStatus.COMPLETED,
            started_at=plan_started,
            provider="deterministic",
            model="investigation-planner",
            summary=(
                "Created the investigation plan and selected bounded "
                "sub-questions."
            ),
            output_references=[
                question.id for question in selected_questions
            ],
        )

        rate_limited = False
        for sub_question in selected_questions:
            research_started = self._now()
            try:
                research_result = await self._research_agent.research(
                    sub_question,
                    max_sources=request.max_sources_per_question,
                )
            except SearchProviderRateLimitError as exc:
                failure = self._provider_failure(exc)
                errors.append(failure)
                rate_limited = True
                warnings.append(
                    "Grounded research was rate-limited. No mock sources were "
                    "substituted, and remaining research calls were stopped."
                )
                self._append_step(
                    audit,
                    step_name=f"research_{sub_question.id}",
                    status=AgentStepStatus.FAILED,
                    started_at=research_started,
                    provider=self._research_agent.provider_name,
                    model=self._research_agent.model_name,
                    summary=(
                        "Grounded research failed because provider quota was "
                        "unavailable."
                    ),
                    input_references=[sub_question.id],
                    errors=[failure],
                )
                break
            except SearchProviderError as exc:
                failure = self._provider_failure(exc)
                errors.append(failure)
                warnings.append(
                    f"Research failed for {sub_question.id}; other bounded "
                    "sub-questions were allowed to continue."
                )
                self._append_step(
                    audit,
                    step_name=f"research_{sub_question.id}",
                    status=AgentStepStatus.FAILED,
                    started_at=research_started,
                    provider=self._research_agent.provider_name,
                    model=self._research_agent.model_name,
                    summary="Grounded research failed for one sub-question.",
                    input_references=[sub_question.id],
                    errors=[failure],
                )
                continue

            all_sources.extend(research_result.sources)
            self._append_step(
                audit,
                step_name=f"research_{sub_question.id}",
                status=AgentStepStatus.COMPLETED,
                started_at=research_started,
                provider=research_result.provider_used,
                model=research_result.model_used,
                summary=(
                    "Researched one selected sub-question and preserved "
                    "normalized sources and grounding metadata."
                ),
                input_references=[sub_question.id],
                output_references=[
                    source.source_id for source in research_result.sources
                ],
                source_count=len(research_result.sources),
                warnings=research_result.warnings,
            )

            evidence_sources = research_result.sources
            rag_warnings: list[str] = []
            if uses_rag and research_result.sources:
                rag_started = self._now()
                index_result = await self._rag_indexing_service.index(
                    IndexRequest(
                        sources=build_index_sources(
                            research_result.sources
                        )
                    )
                )
                if index_result.failures:
                    rag_warnings.append(
                        "RAG indexing failed for one or more normalized "
                        "sources; failed sources were not sent to evidence "
                        "extraction."
                    )
                self._append_step(
                    audit,
                    step_name=f"rag_index_{sub_question.id}",
                    status=(
                        AgentStepStatus.PARTIAL
                        if index_result.failures
                        else AgentStepStatus.COMPLETED
                    ),
                    started_at=rag_started,
                    provider=index_result.provider_used,
                    model=index_result.model_used,
                    summary=(
                        "Chunked and indexed normalized source content for "
                        "semantic retrieval."
                    ),
                    input_references=[
                        source.source_id
                        for source in research_result.sources
                    ],
                    source_count=index_result.sources_indexed,
                    warnings=rag_warnings,
                )

                retrieval_started = self._now()
                retrieved: list[RetrievalResult] = []
                if not index_result.failures:
                    retrieved = await self._rag_retrieval_service.retrieve(
                        RetrievalRequest(
                            query=sub_question.question,
                            top_k=min(
                                request.max_sources_per_question * 4,
                                100,
                            ),
                            source_ids=[
                                source.source_id
                                for source in research_result.sources
                            ],
                            source_urls=[
                                source.url
                                for source in research_result.sources
                            ],
                        )
                    )
                evidence_sources = grounded_sources_from_results(
                    research_result.sources,
                    retrieved,
                    limit=request.max_sources_per_question,
                )
                if not evidence_sources:
                    rag_warnings.append(
                        "RAG retrieval returned no validated grounded chunks; "
                        "no original source text was substituted."
                    )
                self._append_step(
                    audit,
                    step_name=f"rag_retrieve_{sub_question.id}",
                    status=(
                        AgentStepStatus.COMPLETED
                        if evidence_sources
                        else AgentStepStatus.PARTIAL
                    ),
                    started_at=retrieval_started,
                    provider=index_result.provider_used,
                    model=index_result.model_used,
                    summary=(
                        "Retrieved and provenance-validated chunks for one "
                        "selected sub-question."
                    ),
                    input_references=[sub_question.id],
                    output_references=[
                        result.chunk_id for result in retrieved
                    ],
                    source_count=len(evidence_sources),
                    warnings=rag_warnings,
                )
                warnings.extend(rag_warnings)
            elif uses_rag:
                rag_warnings.append(
                    "No usable normalized source content was available for "
                    "RAG indexing or retrieval."
                )
                warnings.extend(rag_warnings)

            evidence_started = self._now()
            evidence_result = await self._evidence_agent.extract(
                plan.query,
                sub_question,
                evidence_sources,
                evidence_id_start=len(all_evidence) + 1,
            )
            evidence_errors = [
                self._provider_failure(failure.error)
                for failure in evidence_result.failures
            ]
            errors.extend(evidence_errors)
            all_evidence.extend(evidence_result.evidence_items)
            self._append_step(
                audit,
                step_name=f"evidence_{sub_question.id}",
                status=(
                    AgentStepStatus.PARTIAL
                    if evidence_errors
                    else AgentStepStatus.COMPLETED
                ),
                started_at=evidence_started,
                provider=self._evidence_agent.provider_name,
                model=self._evidence_agent.model_name,
                summary=(
                    "Extracted and independently validated source-grounded "
                    "evidence for one sub-question."
                ),
                input_references=[
                    source.source_id for source in evidence_sources
                ],
                output_references=[
                    item.evidence_id
                    for item in evidence_result.evidence_items
                ],
                source_count=len(evidence_sources),
                evidence_count=len(evidence_result.evidence_items),
                warnings=evidence_result.warnings,
                errors=evidence_errors,
            )

            conflict_report = self._conflict_service.detect(
                sub_question,
                evidence_result.evidence_items,
            )
            conflicts.append(conflict_report)
            question_results.append(
                AgenticQuestionResult(
                    sub_question=sub_question,
                    status="partial" if evidence_errors else "completed",
                    research=research_result,
                    evidence_items=evidence_result.evidence_items,
                    stance_counts=self._stance_counts(
                        evidence_result.evidence_items
                    ),
                    conflicts=conflict_report,
                    warnings=[
                        *rag_warnings,
                        *evidence_result.warnings,
                    ],
                    errors=evidence_errors,
                )
            )

        conflict_started = self._now()
        self._append_step(
            audit,
            step_name="conflicts_detected",
            status=AgentStepStatus.COMPLETED,
            started_at=conflict_started,
            provider="local",
            model="deterministic-conflict-detector",
            summary=(
                "Compared evidence stances for each completed question and "
                "recorded unresolved source conflicts."
            ),
            input_references=[item.evidence_id for item in all_evidence],
            output_references=[
                report.sub_question_id for report in conflicts
            ],
            evidence_count=len(all_evidence),
        )

        graph_context_lines: list[str] = []
        if request.use_graph_rag:
            graph_started = self._now()
            investigation_id = self._investigation_id(plan.query)
            graph_build_result = await self._graph_builder_service.build(
                GraphBuildRequest(
                    investigation_id=investigation_id,
                    query=plan.query,
                    depth=plan.depth,
                    sub_questions=selected_questions,
                    sources=all_sources,
                    evidence_items=all_evidence,
                    conflicts=conflicts,
                )
            )
            self._append_step(
                audit,
                step_name="graph_build",
                status=AgentStepStatus.COMPLETED,
                started_at=graph_started,
                provider=self._graph_builder_service.provider_name,
                model=self._graph_builder_service.model_name,
                summary=(
                    "Built and updated the knowledge graph from all "
                    "normalized sources, evidence items, and conflicts."
                ),
                input_references=[
                    source.source_id for source in all_sources
                ],
                source_count=graph_build_result.sources_built,
                evidence_count=graph_build_result.evidence_built,
                warnings=graph_build_result.warnings,
            )

            for sub_question in selected_questions:
                rag_started = self._now()
                graph_rag_result = await self._graph_rag_service.search(
                    GraphRAGRequest(
                        query=sub_question.question,
                        investigation_id=investigation_id,
                    )
                )
                graph_context_lines.append(
                    self._graph_rag_summary(
                        sub_question.id,
                        graph_rag_result,
                    )
                )
                self._append_step(
                    audit,
                    step_name=f"graph_rag_{sub_question.id}",
                    status=AgentStepStatus.COMPLETED,
                    started_at=rag_started,
                    provider="graph_rag",
                    model="vector+graph_retriever",
                    summary=(
                        "Retrieved and merged vector and graph context for "
                        "one selected sub-question."
                    ),
                    input_references=[sub_question.id],
                    output_references=[
                        node.node_id
                        for node in graph_rag_result.graph_matches
                    ],
                    source_count=len(graph_rag_result.vector_matches),
                    evidence_count=len(graph_rag_result.graph_matches),
                )

        critic_started = self._now()
        pre_critic_evidence_ids = [
            item.evidence_id for item in all_evidence
        ]
        if not request.run_critic:
            critic_result = CriticAgent.skipped()
            self._append_step(
                audit,
                step_name="critic_executed",
                status=AgentStepStatus.SKIPPED,
                started_at=critic_started,
                provider="local",
                model="bounded-devils-advocate",
                summary="Skipped the critic because run_critic was false.",
            )
        elif rate_limited:
            critic_result = self._critic_blocked_by_rate_limit(
                request.max_critic_rounds,
                errors[-1],
            )
            self._append_step(
                audit,
                step_name="critic_executed",
                status=AgentStepStatus.PARTIAL,
                started_at=critic_started,
                provider=self._research_agent.provider_name,
                model=self._research_agent.model_name,
                summary=(
                    "Skipped additional critic research after the grounded "
                    "search provider was rate-limited."
                ),
                errors=[errors[-1]],
            )
        else:
            critic_result = await self._critic_agent.run(
                original_query=plan.query,
                current_evidence=all_evidence,
                known_sources=all_sources,
                investigation_context=(
                    f"category={plan.category.value}; "
                    f"selected_questions={len(selected_questions)}; "
                    + " ".join(graph_context_lines)
                ),
                max_rounds=request.max_critic_rounds,
                max_sources_per_query=request.max_sources_per_question,
                evidence_id_start=len(all_evidence) + 1,
            )
            errors.extend(critic_result.errors)
            all_sources.extend(critic_result.new_sources)
            all_evidence.extend(critic_result.new_evidence_items)
            warnings.extend(critic_result.warnings)
            critic_conflicts = self._critic_conflicts(critic_result)
            conflicts.extend(critic_conflicts)
            self._append_step(
                audit,
                step_name="critic_executed",
                status=(
                    AgentStepStatus.PARTIAL
                    if critic_result.errors
                    else AgentStepStatus.COMPLETED
                ),
                started_at=critic_started,
                provider=self._research_agent.provider_name,
                model=self._research_agent.model_name,
                summary=(
                    "Executed bounded devil's-advocate research and "
                    "distinguished opposing evidence from missing evidence."
                ),
                input_references=pre_critic_evidence_ids,
                output_references=critic_result.opposing_evidence_ids,
                source_count=len(critic_result.new_sources),
                evidence_count=len(critic_result.new_evidence_items),
                warnings=critic_result.warnings,
                errors=critic_result.errors,
            )

        synthesis_started = self._now()
        synthesis = self._synthesis_agent.synthesize(
            query=plan.query,
            evidence_items=all_evidence,
            conflicts=conflicts,
            critic_result=critic_result,
            errors=errors,
            graph_context=graph_context_lines,
        )
        self._append_step(
            audit,
            step_name="synthesis_produced",
            status=AgentStepStatus.COMPLETED,
            started_at=synthesis_started,
            provider="local",
            model="evidence-picture-synthesizer",
            summary=(
                "Produced a non-verdict synthesis and confidence in the "
                "evidence picture."
            ),
            input_references=[item.evidence_id for item in all_evidence],
            evidence_count=len(all_evidence),
        )

        status = self._final_status(
            errors=errors,
            question_results=question_results,
            critic_result=critic_result,
        )
        state = InvestigationState(
            query=plan.query,
            depth=plan.depth,
            status=status,
            plan=plan,
            selected_sub_questions=selected_questions,
            question_results=question_results,
            critic_result=critic_result,
            conflicts=conflicts,
            synthesis=synthesis,
            audit_trail=audit,
            warnings=warnings,
            errors=errors,
            total_source_count=len(
                {str(source.url) for source in all_sources}
            ),
            total_evidence_count=len(all_evidence),
        )
        return AgenticInvestigationResult(status=status, state=state)

    def _append_step(
        self,
        audit: list[AgentStep],
        *,
        step_name: str,
        status: AgentStepStatus,
        started_at: datetime,
        provider: str | None,
        model: str | None,
        summary: str,
        input_references: list[str] | None = None,
        output_references: list[str] | None = None,
        source_count: int = 0,
        evidence_count: int = 0,
        warnings: list[str] | None = None,
        errors: list[ProviderFailure] | None = None,
    ) -> None:
        audit.append(
            AgentStep(
                step_id=f"step-{len(audit) + 1:03d}",
                step_name=step_name,
                status=status,
                started_at=started_at,
                completed_at=self._now(),
                provider_used=provider,
                model_used=model,
                action_summary=summary,
                input_references=input_references or [],
                output_references=output_references or [],
                source_count=source_count,
                evidence_count=evidence_count,
                warnings=warnings or [],
                errors=errors or [],
            )
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def _assert_limits(cls, request: AgenticInvestigationRequest) -> None:
        if request.max_sub_questions > cls.HARD_MAX_SUB_QUESTIONS:
            raise ValueError("Agentic sub-question hard limit exceeded.")
        if request.max_sources_per_question > cls.HARD_MAX_SOURCES_PER_QUESTION:
            raise ValueError("Agentic source hard limit exceeded.")
        if request.max_critic_rounds > cls.HARD_MAX_CRITIC_ROUNDS:
            raise ValueError("Agentic critic-round hard limit exceeded.")

    @staticmethod
    def _stance_counts(
        evidence_items: Sequence[EvidenceItem],
    ) -> EvidenceStanceCounts:
        counts = Counter(item.stance for item in evidence_items)
        return EvidenceStanceCounts(
            supports=counts[EvidenceStance.SUPPORTS],
            contradicts=counts[EvidenceStance.CONTRADICTS],
            neutral=counts[EvidenceStance.NEUTRAL],
            insufficient=counts[EvidenceStance.INSUFFICIENT],
        )

    def _critic_conflicts(
        self,
        critic_result: CriticResult,
    ) -> list[EvidenceConflictReport]:
        reports: list[EvidenceConflictReport] = []
        for question in critic_result.counter_questions:
            items = [
                item
                for item in critic_result.new_evidence_items
                if item.sub_question_id == question.id
            ]
            if items:
                reports.append(self._conflict_service.detect(question, items))
        return reports

    @staticmethod
    def _critic_blocked_by_rate_limit(
        rounds_requested: int,
        error: ProviderFailure,
    ) -> CriticResult:
        return CriticResult(
            status="partial",
            enabled=True,
            rounds_requested=rounds_requested,
            rounds_completed=0,
            counter_questions=[],
            assumptions_challenged=[],
            research_results=[],
            new_sources=[],
            new_evidence_items=[],
            opposing_evidence_ids=[],
            finding_summary=(
                "Critic research could not run because grounded search was "
                "rate-limited. No mock sources were substituted."
            ),
            warnings=[
                "The critic was bounded and did not retry after the primary "
                "research rate-limit failure."
            ],
            errors=[error],
        )

    @staticmethod
    def _final_status(
        *,
        errors: Sequence[ProviderFailure],
        question_results: Sequence[AgenticQuestionResult],
        critic_result: CriticResult,
    ) -> str:
        if not errors:
            return "completed"
        if question_results or critic_result.new_evidence_items:
            return "partial"
        return "failed"

    @staticmethod
    def _investigation_id(query: str) -> str:
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        return f"inv-{digest[:12]}"

    @staticmethod
    def _graph_rag_summary(
        sub_question_id: str,
        result: GraphRAGResult,
    ) -> str:
        return (
            f"{sub_question_id}: {len(result.vector_matches)} vector "
            f"match(es), {len(result.graph_matches)} graph node(s), "
            f"{len(result.graph_paths)} path(s), "
            f"{len(result.merged_context)} merged context item(s)"
        )

    @staticmethod
    def _provider_failure(
        exc: SearchProviderError | EvidenceProviderError,
    ) -> ProviderFailure:
        return ProviderFailure(
            error_type=exc.error_type,
            provider=exc.provider,
            model=exc.model,
            message=exc.message,
            retryable=exc.retryable,
            retry_after_seconds=exc.retry_after_seconds,
        )
