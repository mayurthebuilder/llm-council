from __future__ import annotations

import asyncio
import json

import pytest

from llm_council.providers.base import CompletionRequest, Provider
from llm_council.providers.fake import DeterministicProvider


def _request(phase: str) -> CompletionRequest:
    return CompletionRequest(
        phase=phase,
        system="Return a structured decision.",
        user="A fictional billing decision.",
        metadata={"advisor_id": "advisor-1", "lens": "strategy"},
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

    await asyncio.gather(provider.complete(_request("advisor")), provider.complete(_request("review")))

    assert len(provider.request_timestamps) == 2
    assert {record.request.phase for record in provider.request_timestamps} == {"advisor", "review"}
    assert all(record.started_at <= record.completed_at for record in provider.request_timestamps)


def test_provider_protocol_is_runtime_checkable() -> None:
    """A provider with the public completion method must satisfy the boundary protocol."""

    assert isinstance(DeterministicProvider(), Provider)
