import re
from typing import ClassVar

from app.schemas.investigation import (
    InvestigationCategory,
    InvestigationDepth,
    InvestigationPlan,
    InvestigationRequest,
    InvestigationSubQuestion,
    ResearchAngle,
    ResearchAngleType,
)


class InvestigationPlanner:
    _SUB_QUESTION_COUNTS: ClassVar[dict[InvestigationDepth, int]] = {
        InvestigationDepth.QUICK: 3,
        InvestigationDepth.STANDARD: 5,
        InvestigationDepth.DEEP: 8,
    }

    _CATEGORY_PATTERNS: ClassVar[
        tuple[
            tuple[InvestigationCategory, tuple[re.Pattern[str], ...]],
            ...,
        ]
    ] = (
        (
            InvestigationCategory.COMPARISON,
            (
                re.compile(r"\b(compare|comparison|versus|vs\.?)\b"),
                re.compile(r"\bdifference(?:s)? between\b"),
                re.compile(r"\bbetter than\b"),
            ),
        ),
        (
            InvestigationCategory.CAUSAL_QUESTION,
            (
                re.compile(r"^\s*why\b"),
                re.compile(
                    r"\b(cause|causes|caused|causal|effect|effects|impact|impacts)\b"
                ),
                re.compile(r"\b(leads? to|results? in)\b"),
                re.compile(r"^\s*how (does|do|did|can)\b"),
            ),
        ),
        (
            InvestigationCategory.CURRENT_EVENT,
            (
                re.compile(
                    r"\b(current|currently|latest|recent|recently|today|ongoing|breaking)\b"
                ),
                re.compile(r"\bthis (week|month|year)\b"),
                re.compile(r"\b202[5-9]\b"),
            ),
        ),
        (
            InvestigationCategory.RESEARCH_TOPIC,
            (
                re.compile(
                    r"\b(research|overview|study|explore|explain|analysis of|tell me about)\b"
                ),
                re.compile(r"^\s*what (is|are)\b"),
            ),
        ),
        (
            InvestigationCategory.FACTUAL_CLAIM,
            (
                re.compile(r"^\s*(is|are|was|were|did|does|do|has|have|can)\b"),
                re.compile(
                    r"\b(fact[- ]?check|verify|true or false|claim(?:s|ed)? that)\b"
                ),
            ),
        ),
    )

    _ANGLE_ORDER: ClassVar[
        dict[InvestigationCategory, tuple[ResearchAngleType, ...]]
    ] = {
        InvestigationCategory.FACTUAL_CLAIM: (
            ResearchAngleType.SUPPORTING_EVIDENCE,
            ResearchAngleType.CONTRADICTING_EVIDENCE,
            ResearchAngleType.SOURCE_CREDIBILITY,
            ResearchAngleType.ALTERNATIVE_EXPLANATIONS,
            ResearchAngleType.LIMITATIONS,
            ResearchAngleType.HISTORICAL_CONTEXT,
            ResearchAngleType.DEFINITIONS_AND_SCOPE,
            ResearchAngleType.RECENT_DEVELOPMENTS,
        ),
        InvestigationCategory.COMPARISON: (
            ResearchAngleType.DEFINITIONS_AND_SCOPE,
            ResearchAngleType.SUPPORTING_EVIDENCE,
            ResearchAngleType.SOURCE_CREDIBILITY,
            ResearchAngleType.CONTRADICTING_EVIDENCE,
            ResearchAngleType.LIMITATIONS,
            ResearchAngleType.HISTORICAL_CONTEXT,
            ResearchAngleType.ALTERNATIVE_EXPLANATIONS,
            ResearchAngleType.RECENT_DEVELOPMENTS,
        ),
        InvestigationCategory.CAUSAL_QUESTION: (
            ResearchAngleType.SUPPORTING_EVIDENCE,
            ResearchAngleType.ALTERNATIVE_EXPLANATIONS,
            ResearchAngleType.CONTRADICTING_EVIDENCE,
            ResearchAngleType.SOURCE_CREDIBILITY,
            ResearchAngleType.HISTORICAL_CONTEXT,
            ResearchAngleType.LIMITATIONS,
            ResearchAngleType.DEFINITIONS_AND_SCOPE,
            ResearchAngleType.RECENT_DEVELOPMENTS,
        ),
        InvestigationCategory.RESEARCH_TOPIC: (
            ResearchAngleType.DEFINITIONS_AND_SCOPE,
            ResearchAngleType.SOURCE_CREDIBILITY,
            ResearchAngleType.HISTORICAL_CONTEXT,
            ResearchAngleType.SUPPORTING_EVIDENCE,
            ResearchAngleType.CONTRADICTING_EVIDENCE,
            ResearchAngleType.LIMITATIONS,
            ResearchAngleType.ALTERNATIVE_EXPLANATIONS,
            ResearchAngleType.RECENT_DEVELOPMENTS,
        ),
        InvestigationCategory.CURRENT_EVENT: (
            ResearchAngleType.RECENT_DEVELOPMENTS,
            ResearchAngleType.SOURCE_CREDIBILITY,
            ResearchAngleType.SUPPORTING_EVIDENCE,
            ResearchAngleType.CONTRADICTING_EVIDENCE,
            ResearchAngleType.HISTORICAL_CONTEXT,
            ResearchAngleType.ALTERNATIVE_EXPLANATIONS,
            ResearchAngleType.LIMITATIONS,
            ResearchAngleType.DEFINITIONS_AND_SCOPE,
        ),
        InvestigationCategory.GENERAL_INVESTIGATION: (
            ResearchAngleType.DEFINITIONS_AND_SCOPE,
            ResearchAngleType.SUPPORTING_EVIDENCE,
            ResearchAngleType.SOURCE_CREDIBILITY,
            ResearchAngleType.CONTRADICTING_EVIDENCE,
            ResearchAngleType.HISTORICAL_CONTEXT,
            ResearchAngleType.LIMITATIONS,
            ResearchAngleType.ALTERNATIVE_EXPLANATIONS,
            ResearchAngleType.RECENT_DEVELOPMENTS,
        ),
    }

    _ANGLE_DESCRIPTIONS: ClassVar[dict[ResearchAngleType, str]] = {
        ResearchAngleType.SUPPORTING_EVIDENCE: (
            "Identify reliable evidence that supports the central assertions."
        ),
        ResearchAngleType.CONTRADICTING_EVIDENCE: (
            "Actively look for evidence that challenges or weakens the assertions."
        ),
        ResearchAngleType.SOURCE_CREDIBILITY: (
            "Assess source authority, independence, methodology, and potential bias."
        ),
        ResearchAngleType.HISTORICAL_CONTEXT: (
            "Establish the background and timeline needed to interpret the topic."
        ),
        ResearchAngleType.LIMITATIONS: (
            "Identify uncertainty, evidence gaps, and methodological constraints."
        ),
        ResearchAngleType.ALTERNATIVE_EXPLANATIONS: (
            "Consider other plausible explanations or interpretations."
        ),
        ResearchAngleType.DEFINITIONS_AND_SCOPE: (
            "Clarify key terms, entities, timeframe, and investigation boundaries."
        ),
        ResearchAngleType.RECENT_DEVELOPMENTS: (
            "Check for recent changes that could alter the investigation context."
        ),
    }

    _QUESTION_TEMPLATES: ClassVar[dict[ResearchAngleType, str]] = {
        ResearchAngleType.SUPPORTING_EVIDENCE: (
            'What reliable evidence supports the central assertions in "{query}"?'
        ),
        ResearchAngleType.CONTRADICTING_EVIDENCE: (
            'What credible evidence contradicts or weakens the assertions in "{query}"?'
        ),
        ResearchAngleType.SOURCE_CREDIBILITY: (
            'Which primary or authoritative sources are best suited to investigate "{query}", and why?'
        ),
        ResearchAngleType.HISTORICAL_CONTEXT: (
            'What historical context and timeline are necessary to understand "{query}"?'
        ),
        ResearchAngleType.LIMITATIONS: (
            'What evidence gaps, uncertainties, or methodological limitations affect "{query}"?'
        ),
        ResearchAngleType.ALTERNATIVE_EXPLANATIONS: (
            'What plausible alternative explanations or interpretations should be considered for "{query}"?'
        ),
        ResearchAngleType.DEFINITIONS_AND_SCOPE: (
            'Which terms, entities, timeframe, and scope must be defined for "{query}"?'
        ),
        ResearchAngleType.RECENT_DEVELOPMENTS: (
            'Which recent developments could materially change the understanding of "{query}"?'
        ),
    }

    def plan(self, request: InvestigationRequest) -> InvestigationPlan:
        category = self.detect_category(request.query)
        selected_angles = self._select_angles(category, request.depth)

        research_angles = [
            ResearchAngle(
                angle=angle,
                description=self._ANGLE_DESCRIPTIONS[angle],
            )
            for angle in selected_angles
        ]
        sub_questions = [
            InvestigationSubQuestion(
                id=f"sq-{priority:02d}",
                question=self._QUESTION_TEMPLATES[angle].format(
                    query=request.query
                ),
                purpose=self._ANGLE_DESCRIPTIONS[angle],
                priority=priority,
            )
            for priority, angle in enumerate(selected_angles, start=1)
        ]

        return InvestigationPlan(
            query=request.query,
            depth=request.depth,
            category=category,
            research_angles=research_angles,
            sub_questions=sub_questions,
        )

    def detect_category(self, query: str) -> InvestigationCategory:
        normalized_query = query.casefold()
        for category, patterns in self._CATEGORY_PATTERNS:
            if any(pattern.search(normalized_query) for pattern in patterns):
                return category
        return InvestigationCategory.GENERAL_INVESTIGATION

    def _select_angles(
        self,
        category: InvestigationCategory,
        depth: InvestigationDepth,
    ) -> tuple[ResearchAngleType, ...]:
        count = self._SUB_QUESTION_COUNTS[depth]
        return self._ANGLE_ORDER[category][:count]
