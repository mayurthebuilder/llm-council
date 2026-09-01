from __future__ import annotations

import asyncio
import json

import pytest

from llm_council.models import AdvisorResult, CouncilDecision, PeerReview
from llm_council.parsing import parse_model
from llm_council.providers.base import CompletionRequest, Provider
from llm_council.providers.fake import DeterministicProvider


def _request(phase: str) -> CompletionRequest:
    return CompletionRequest(
        phase=phase,
        system="Return a structured decision.",
        user="A fictional B2B SaaS digital marketing launch.",
        metadata={
            "advisor_id": "advisor-1",
            "lens": "strategy",
            "candidate_response_ids": ["Response B", "Response D"],
            "advisor_count": 3,
            "review_count": 2,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phase", "required_keys", "has_recommendation"),
    [
        (
            "advisor",
            {
                "analysis",
                "recommendation",
                "assumptions",
                "evidence_references",
                "risks",
            },
            True,
        ),
        (
            "review",
            {"reviewer_id", "ranked_response_ids", "critique", "missing_evidence"},
            False,
        ),
        (
            "chairman",
            {
                "recommendation",
                "rationale",
                "consensus",
                "dissent",
                "assumptions",
                "risks",
                "next_actions",
                "confidence",
            },
            True,
        ),
    ],
)
async def test_fake_provider_returns_phase_specific_json(
    phase: str, required_keys: set[str], has_recommendation: bool
) -> None:
    """A missing phase payload must not silently reach the strict parser."""

    payload = json.loads(await DeterministicProvider().complete(_request(phase)))

    assert required_keys <= payload.keys()
    assert ("recommendation" in payload) is has_recommendation


@pytest.mark.asyncio
async def test_fake_provider_returns_identical_json_for_identical_request() -> None:
    """A changed fake response must remain reproducible for offline tests."""

    provider = DeterministicProvider()
    request = _request("advisor")

    assert await provider.complete(request) == await provider.complete(request)


@pytest.mark.asyncio
async def test_fake_provider_records_completion_timestamps() -> None:
    """Removing timing records would prevent later concurrency inspection."""

    provider = DeterministicProvider(delay_seconds=0.001)

    await asyncio.gather(
        provider.complete(_request("advisor")), provider.complete(_request("review"))
    )

    assert len(provider.request_timestamps) == 2
    assert {record.request.phase for record in provider.request_timestamps} == {"advisor", "review"}
    assert all(record.started_at <= record.completed_at for record in provider.request_timestamps)


def test_provider_protocol_is_runtime_checkable() -> None:
    """A provider with the public completion method must satisfy the boundary protocol."""

    assert isinstance(DeterministicProvider(), Provider)


@pytest.mark.asyncio
async def test_fake_advisor_payload_has_required_response_id() -> None:
    """A missing response ID prevents strict parsing in real orchestration."""
    provider = DeterministicProvider()
    advisor = parse_model(await provider.complete(_request("advisor")), AdvisorResult)
    assert advisor.response_id


@pytest.mark.asyncio
async def test_fake_review_ranks_actual_candidates() -> None:
    """A hardcoded label can rank a nonexistent candidate."""
    provider = DeterministicProvider()
    review = parse_model(await provider.complete(_request("review")), PeerReview)
    assert review.ranked_response_ids == ["Response B", "Response D"]


@pytest.mark.asyncio
async def test_fake_chairman_uses_actual_counts() -> None:
    """Hardcoded counts misrepresent quorum-degraded runs."""
    provider = DeterministicProvider()
    chairman = parse_model(await provider.complete(_request("chairman")), CouncilDecision)
    assert (chairman.advisor_count, chairman.review_count) == (3, 2)


@pytest.mark.asyncio
async def test_fake_demo_is_marketing_specific_and_names_seo_aeo_geo() -> None:
    provider = DeterministicProvider()

    advisor = parse_model(await provider.complete(_request("advisor")), AdvisorResult)
    review = parse_model(await provider.complete(_request("review")), PeerReview)
    chairman = parse_model(await provider.complete(_request("chairman")), CouncilDecision)
    rendered = json.dumps(
        {
            "advisor": advisor.model_dump(),
            "review": review.model_dump(),
            "chairman": chairman.model_dump(),
        }
    )

    assert "digital marketing" in rendered.lower()
    for capability in ("SEO", "AEO", "GEO"):
        assert capability in rendered
    assert "billing" not in rendered.lower()
