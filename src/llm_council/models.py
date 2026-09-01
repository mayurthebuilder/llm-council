"""Validated, serializable domain models for the council workflow."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TextList = Annotated[list[NonBlankText], Field(min_length=1)]


class CouncilModel(BaseModel):
    """Base model that rejects unknown data and cannot be mutated after validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvisorSpec(CouncilModel):
    """A distinct analytical perspective used for one advisor response."""

    advisor_id: NonBlankText
    lens: NonBlankText
    instructions: NonBlankText = "Analyze the decision through this lens."


DEFAULT_ADVISORS: tuple[AdvisorSpec, ...] = (
    AdvisorSpec(
        advisor_id="advisor-1",
        lens="brand and audience strategy",
        instructions=(
            "Assess positioning, segmentation, customer insight, messaging, "
            "differentiation, and brand consistency. Separate supplied audience facts "
            "from hypotheses that require research."
        ),
    ),
    AdvisorSpec(
        advisor_id="advisor-2",
        lens="growth and channel strategy",
        instructions=(
            "Assess acquisition and lifecycle strategy, paid and organic channel mix, "
            "funnel design, budget tradeoffs, and testable experiments."
        ),
    ),
    AdvisorSpec(
        advisor_id="advisor-3",
        lens="SEO, AEO, and GEO strategy",
        instructions=(
            "Assess conventional SEO foundations, answer engine optimization (AEO), "
            "and generative engine optimization (GEO) through crawlability, entity "
            "clarity, original evidence, answer-first content, expert attribution, and "
            "valid structured data. Identify missing current search-platform evidence. "
            "Do not promise rankings, citations, traffic, or revenue."
        ),
    ),
    AdvisorSpec(
        advisor_id="advisor-4",
        lens="creative and content strategy",
        instructions=(
            "Assess campaign concepts, content systems, distribution formats, conversion "
            "journeys, and creative feasibility while preserving brand consistency."
        ),
    ),
    AdvisorSpec(
        advisor_id="advisor-5",
        lens="measurement and marketing risk",
        instructions=(
            "Assess KPI design, incrementality, attribution limits, privacy, compliance, "
            "reputational risk, and unsupported assumptions. Require measurable tests "
            "without presenting modeled outcomes as facts."
        ),
    ),
)


class CouncilConfig(CouncilModel):
    """Run settings that do not contain user prompts, outputs, or credentials."""

    advisor_timeout_seconds: Annotated[float, Field(gt=0, le=300)] = 30.0
    min_advisors: Annotated[int, Field(ge=1, le=5)] = 3
    min_reviews: Annotated[int, Field(ge=0, le=5)] = 2
    random_seed: int | None = None


class CouncilRequest(CouncilModel):
    """The explicit question and optional user-supplied context for a run."""

    question: NonBlankText
    context: NonBlankText | None = None
    config: CouncilConfig = Field(default_factory=CouncilConfig)


class AdvisorResult(CouncilModel):
    """Normalized analysis from an anonymous advisor response."""

    response_id: NonBlankText
    analysis: NonBlankText
    recommendation: NonBlankText
    assumptions: TextList
    evidence_references: TextList
    risks: TextList


class PeerReview(CouncilModel):
    """Blind review of anonymously labelled advisor responses."""

    reviewer_id: NonBlankText
    ranked_response_ids: TextList
    critique: NonBlankText
    missing_evidence: TextList


class CouncilDecision(CouncilModel):
    """Chairman synthesis with material agreement, disagreement, and action."""

    recommendation: NonBlankText
    rationale: TextList
    consensus: TextList
    dissent: TextList
    assumptions: TextList
    risks: TextList
    next_actions: TextList
    confidence: Literal["low", "moderate", "high"]
    advisor_count: Annotated[int, Field(ge=1, le=5)]
    review_count: Annotated[int, Field(ge=0, le=5)]
    execution_metadata: dict[str, int | float | bool | None] = Field(default_factory=dict)
