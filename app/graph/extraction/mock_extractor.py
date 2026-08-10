import asyncio
import re
from collections.abc import Sequence
from typing import ClassVar

from app.graph.extraction.base import (
    ExtractedEntity,
    ExtractedRelation,
    GraphExtractionProvider,
    GraphExtractionResult,
)
from app.graph.models import (
    GraphNodeType,
    GraphRelationType,
)


class MockGraphExtractionProvider(GraphExtractionProvider):
    """Deterministic, offline entity/relation extraction from supplied text.

    Rules are deliberately simple and documented so development behavior is
    stable: acronyms are organizations; capitalized phrases are classified by
    known keywords, a small built-in location gazetteer, or the preceding word;
    entities in the same sentence are related.
    """

    _ORGANIZATION_KEYWORDS: ClassVar[frozenset[str]] = frozenset(
        {
            "agency",
            "association",
            "authority",
            "commission",
            "company",
            "corporation",
            "council",
            "department",
            "foundation",
            "institute",
            "ltd",
            "media",
            "ministry",
            "news",
            "organization",
            "university",
        }
    )
    _LOCATION_GAZETTEER: ClassVar[frozenset[str]] = frozenset(
        {
            "berlin",
            "brussels",
            "canberra",
            "geneva",
            "london",
            "madrid",
            "new york",
            "oslo",
            "paris",
            "stockholm",
            "tokyo",
            "toronto",
            "vienna",
            "washington",
        }
    )
    _EVENT_KEYWORDS: ClassVar[frozenset[str]] = frozenset(
        {
            "announcement",
            "conference",
            "decision",
            "election",
            "hearing",
            "launch",
            "meeting",
            "release",
            "report",
            "study",
            "trial",
        }
    )
    _PERSON_INDICATORS: ClassVar[frozenset[str]] = frozenset(
        {
            "according",
            "authored",
            "by",
            "dr",
            "interviewed",
            "mr",
            "mrs",
            "ms",
            "prof",
            "said",
            "says",
            "stated",
            "wrote",
        }
    )
    _ACRONYM_PATTERN = re.compile(r"\b[A-Z]{2,6}\b")
    _PHRASE_PATTERN = re.compile(
        r"[A-Z][a-z]+(?:[ \u00a0][A-Z][a-z]+)+"
    )
    _CAPITALIZED_WORD_PATTERN = re.compile(r"\b[A-Z][a-z]+\b")

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-graph-extractor"

    async def extract_entities_and_relations(
        self,
        *,
        source_id: str,
        source_url: str,
        content: str,
    ) -> GraphExtractionResult:
        await asyncio.sleep(0)
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("content must not be empty")
        if not source_id.strip() or not source_url.strip():
            raise ValueError("source_id and source_url are required")

        entities = self._extract_entities(normalized_content)
        relations = self._extract_relations(normalized_content, entities)
        return GraphExtractionResult(
            provider_used=self.provider_name,
            model_used=self.model_name,
            entities=entities,
            relations=relations,
        )

    def _extract_entities(self, content: str) -> list[ExtractedEntity]:
        candidates: list[tuple[str, int]] = []
        for match in self._PHRASE_PATTERN.finditer(content):
            candidates.append((match.group(0), match.start()))
        acronyms = {
            match.group(0)
            for match in self._ACRONYM_PATTERN.finditer(content)
        }
        covered_ranges: list[tuple[int, int]] = [
            (match.start(), match.end())
            for match in self._PHRASE_PATTERN.finditer(content)
        ]
        for match in self._CAPITALIZED_WORD_PATTERN.finditer(content):
            word = match.group(0)
            if any(
                start <= match.start() < end
                for start, end in covered_ranges
            ):
                continue
            previous_word = self._previous_word(content, match.start())
            if previous_word is not None:
                candidates.append((word, match.start()))

        seen_names: set[str] = set()
        entities: list[ExtractedEntity] = []
        for name, start in candidates:
            normalized_name = " ".join(name.split())
            if normalized_name.casefold() in seen_names:
                continue
            seen_names.add(normalized_name.casefold())
            node_type = self._classify(
                normalized_name,
                previous_word=self._previous_word(content, start),
            )
            if node_type is None:
                continue
            entities.append(
                ExtractedEntity(
                    name=normalized_name,
                    node_type=node_type,
                    metadata={"classification": "deterministic_mock_heuristics"},
                )
            )

        for acronym in sorted(acronyms):
            if acronym.casefold() in seen_names:
                continue
            seen_names.add(acronym.casefold())
            entities.append(
                ExtractedEntity(
                    name=acronym,
                    node_type=GraphNodeType.ORGANIZATION,
                    metadata={"classification": "deterministic_mock_acronym"},
                )
            )
        entities.sort(key=lambda entity: entity.name)
        return entities

    def _extract_relations(
        self,
        content: str,
        entities: Sequence[ExtractedEntity],
    ) -> list[ExtractedRelation]:
        relations: list[ExtractedRelation] = []
        seen: set[tuple[str, str, str]] = set()
        for sentence in re.split(r"[.!?]\s+", content):
            present = [
                entity
                for entity in entities
                if self._is_in(entity.name, sentence)
            ]
            for left_index, left in enumerate(present):
                for right in present[left_index + 1 :]:
                    if left.node_type is GraphNodeType.EVENT and (
                        right.node_type is GraphNodeType.LOCATION
                    ):
                        relation_type = GraphRelationType.OCCURRED_AT
                        source, target = left, right
                    elif right.node_type is GraphNodeType.EVENT and (
                        left.node_type is GraphNodeType.LOCATION
                    ):
                        relation_type = GraphRelationType.OCCURRED_AT
                        source, target = right, left
                    else:
                        relation_type = GraphRelationType.RELATED_TO
                        source, target = left, right
                    key = (
                        source.name,
                        relation_type.value,
                        target.name,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    relations.append(
                        ExtractedRelation(
                            source_name=source.name,
                            relation_type=relation_type,
                            target_name=target.name,
                            confidence=0.5,
                            metadata={
                                "classification": "deterministic_mock_sentence"
                            },
                        )
                    )
        relations.sort(
            key=lambda relation: (
                relation.source_name,
                relation.relation_type.value,
                relation.target_name,
            )
        )
        return relations

    def _classify(
        self,
        name: str,
        *,
        previous_word: str | None,
    ) -> GraphNodeType | None:
        tokens = name.casefold().split()
        if any(token in self._ORGANIZATION_KEYWORDS for token in tokens):
            return GraphNodeType.ORGANIZATION
        if (
            name.casefold() in self._LOCATION_GAZETTEER
        ):
            return GraphNodeType.LOCATION
        if any(token in self._EVENT_KEYWORDS for token in tokens):
            return GraphNodeType.EVENT
        if previous_word is not None and previous_word in self._PERSON_INDICATORS:
            return GraphNodeType.PERSON
        return None

    @staticmethod
    def _previous_word(content: str, position: int) -> str | None:
        prefix = content[:position].rstrip()
        if not prefix:
            return None
        match = re.search(r"([A-Za-z]+)$", prefix)
        if match is None:
            return None
        return match.group(1).casefold()

    @staticmethod
    def _is_in(name: str, sentence: str) -> bool:
        return name.casefold() in sentence.casefold()
