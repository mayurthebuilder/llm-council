from __future__ import annotations

import pytest
from pydantic import ValidationError

from llm_council.models import (
    DEFAULT_ADVISORS,
    AdvisorResult,
    AdvisorSpec,
    CouncilConfig,
    CouncilDecision,
    CouncilRequest,
    PeerReview,
)


def test_request_rejects_blank_question() -> None:
    with pytest.raises(ValidationError):
        CouncilRequest(question="   ")


def test_decision_requires_material_sections() -> None:
    decision = CouncilDecision(
        recommendation="Buy the billing platform for the first year.",
        rationale=["The team has no payments specialist."],
        consensus=["Time to market is the binding constraint."],
        dissent=["A custom ledger could reduce long-run migration cost."],
        assumptions=["Transaction volume remains below the stated threshold."],
        risks=["Vendor lock-in."],
        next_actions=["Run a two-week integration spike."],
        confidence="moderate",
        advisor_count=5,
        review_count=5,
    )
    assert decision.advisor_count == 5


def test_models_are_frozen_and_reject_unknown_fields() -> None:
    request = CouncilRequest(question="Should we build or buy?")
    with pytest.raises(ValidationError):
        request.question = "Changed"
    with pytest.raises(ValidationError):
        CouncilRequest(question="Should we build or buy?", untrusted=True)


def test_default_advisors_cover_the_five_required_lenses() -> None:
    assert [advisor.lens for advisor in DEFAULT_ADVISORS] == [
        "brand and audience strategy",
        "growth and channel strategy",
        "SEO, AEO, and GEO strategy",
        "creative and content strategy",
        "measurement and marketing risk",
    ]


def test_default_advisors_make_digital_marketing_and_search_boundaries_explicit() -> None:
    roster = "\n".join(
        f"{advisor.lens}: {advisor.instructions}" for advisor in DEFAULT_ADVISORS
    )

    for capability in ("SEO", "AEO", "GEO"):
        assert capability in roster
    for boundary in ("rankings", "citations", "traffic", "revenue"):
        assert boundary in roster
    assert "current search-platform evidence" in roster


def test_config_has_safe_default_quorums_and_timeout() -> None:
    assert CouncilConfig() == CouncilConfig(
        advisor_timeout_seconds=30.0,
        min_advisors=3,
        min_reviews=2,
        random_seed=None,
    )


@pytest.mark.parametrize(
    ("model", "field", "value"),
    [
        (AdvisorSpec, "advisor_id", " "),
        (AdvisorResult, "analysis", " "),
        (PeerReview, "critique", " "),
        (CouncilDecision, "recommendation", " "),
    ],
)
def test_domain_text_fields_reject_blank_values(
    model: type[object], field: str, value: str
) -> None:
    valid_advisor = AdvisorSpec(advisor_id="advisor-1", lens="strategy")
    valid_result = AdvisorResult(
        response_id="Response A",
        analysis="A reasoned analysis.",
        recommendation="Choose the hosted service.",
        assumptions=["Demand remains steady."],
        evidence_references=["Brief section 1"],
        risks=["Vendor concentration."],
    )
    valid_review = PeerReview(
        reviewer_id="advisor-2",
        ranked_response_ids=["Response A"],
        critique="The recommendation is supported.",
        missing_evidence=["Pricing data"],
    )
    valid_decision = CouncilDecision(
        recommendation="Choose the hosted service.",
        rationale=["The team can ship sooner."],
        consensus=["Speed is important."],
        dissent=["A custom build offers control."],
        assumptions=["Demand remains steady."],
        risks=["Vendor concentration."],
        next_actions=["Run a pilot."],
        confidence="moderate",
        advisor_count=3,
        review_count=2,
    )
    instances: dict[type[object], object] = {
        AdvisorSpec: valid_advisor,
        AdvisorResult: valid_result,
        PeerReview: valid_review,
        CouncilDecision: valid_decision,
    }
    payload = instances[model].model_dump()  # type: ignore[attr-defined]
    payload[field] = value
    with pytest.raises(ValidationError):
        model(**payload)  # type: ignore[operator]


@pytest.mark.parametrize("advisor_count, review_count", [(0, 2), (6, 2), (3, -1), (3, 6)])
def test_decision_rejects_counts_outside_council_bounds(
    advisor_count: int, review_count: int
) -> None:
    with pytest.raises(ValidationError):
        CouncilDecision(
            recommendation="Choose the hosted service.",
            rationale=["The team can ship sooner."],
            consensus=["Speed is important."],
            dissent=["A custom build offers control."],
            assumptions=["Demand remains steady."],
            risks=["Vendor concentration."],
            next_actions=["Run a pilot."],
            confidence="moderate",
            advisor_count=advisor_count,
            review_count=review_count,
        )
