from pydantic import ValidationError

from app.schemas.investigation import (
    InvestigationCategory,
    InvestigationDepth,
    InvestigationRequest,
)
from app.services.investigation_service import InvestigationPlanner


planner = InvestigationPlanner()


def _assert_invalid_request(**payload: object) -> None:
    try:
        InvestigationRequest.model_validate(payload)
    except ValidationError:
        return
    raise AssertionError("Expected request validation to fail")


def test_valid_standard_request() -> None:
    request = InvestigationRequest(
        query="  Verify the claim that water boils at 100 C  ",
        depth=InvestigationDepth.STANDARD,
    )
    plan = planner.plan(request)

    assert request.query == "Verify the claim that water boils at 100 C"
    assert plan.depth is InvestigationDepth.STANDARD
    assert plan.category is InvestigationCategory.FACTUAL_CLAIM
    assert len(plan.sub_questions) == 5
    assert len(plan.research_angles) == 5


def test_quick_depth() -> None:
    request = InvestigationRequest(
        query="Compare solar power versus wind power",
        depth=InvestigationDepth.QUICK,
    )
    plan = planner.plan(request)

    assert plan.depth is InvestigationDepth.QUICK
    assert len(plan.sub_questions) == 3


def test_deep_depth() -> None:
    request = InvestigationRequest(
        query="Why does sleep affect memory formation?",
        depth=InvestigationDepth.DEEP,
    )
    plan = planner.plan(request)

    assert plan.depth is InvestigationDepth.DEEP
    assert len(plan.sub_questions) == 8


def test_invalid_empty_query() -> None:
    _assert_invalid_request(query="   ", depth="standard")


def test_invalid_short_query() -> None:
    _assert_invalid_request(query="abcd", depth="standard")


def test_invalid_depth() -> None:
    _assert_invalid_request(query="A valid investigation query", depth="extreme")


def test_default_depth() -> None:
    request = InvestigationRequest(query="Research renewable energy storage")

    assert request.depth is InvestigationDepth.STANDARD
    assert len(planner.plan(request).sub_questions) == 5


def test_number_of_generated_sub_questions() -> None:
    expected_counts = {
        InvestigationDepth.QUICK: 3,
        InvestigationDepth.STANDARD: 5,
        InvestigationDepth.DEEP: 8,
    }

    for depth, expected_count in expected_counts.items():
        request = InvestigationRequest(
            query="Investigate unusual patterns in these records",
            depth=depth,
        )
        plan = planner.plan(request)

        assert len(plan.sub_questions) == expected_count
        assert [item.priority for item in plan.sub_questions] == list(
            range(1, expected_count + 1)
        )
        assert [item.id for item in plan.sub_questions] == [
            f"sq-{number:02d}"
            for number in range(1, expected_count + 1)
        ]


def test_category_detection() -> None:
    examples = {
        "Verify the claim that the document is authentic": (
            InvestigationCategory.FACTUAL_CLAIM
        ),
        "Compare electric cars versus gasoline cars": (
            InvestigationCategory.COMPARISON
        ),
        "Why do some materials conduct electricity?": (
            InvestigationCategory.CAUSAL_QUESTION
        ),
        "Research the history of cryptography": (
            InvestigationCategory.RESEARCH_TOPIC
        ),
        "What are the latest developments in battery technology?": (
            InvestigationCategory.CURRENT_EVENT
        ),
        "Investigate unusual patterns in these records": (
            InvestigationCategory.GENERAL_INVESTIGATION
        ),
    }

    for query, expected_category in examples.items():
        assert planner.detect_category(query) is expected_category
