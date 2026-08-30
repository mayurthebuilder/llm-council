"""Deterministic offline provider for tests and demonstrations."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from time import monotonic

from .base import CompletionRequest


@dataclass(frozen=True, slots=True)
class RequestTiming:
    """The start and finish times of one deterministic provider completion."""

    request: CompletionRequest
    started_at: float
    completed_at: float


class DeterministicProvider:
    """Return stable phase-specific JSON without environment or network access."""

    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds
        self.request_timestamps: list[RequestTiming] = []

    async def complete(self, request: CompletionRequest) -> str:
        """Return the fixed structured payload for ``request.phase``."""

        started_at = monotonic()
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        completed_at = monotonic()
        self.request_timestamps.append(
            RequestTiming(request=request, started_at=started_at, completed_at=completed_at)
        )
        return json.dumps(_phase_payload(request), sort_keys=True)


def _phase_payload(request: CompletionRequest) -> dict[str, object]:
    """Build a fixed valid payload for the requested workflow phase."""

    if request.phase == "advisor":
        return {
            "analysis": "The hosted option reduces near-term implementation risk.",
            "recommendation": "Run a time-boxed hosted billing pilot before committing.",
            "assumptions": ["The team needs a launch path within one quarter."],
            "evidence_references": ["The supplied fictional decision brief."],
            "risks": ["A hosted provider can create migration costs."],
        }
    if request.phase == "review":
        return {
            "reviewer_id": str(request.metadata.get("advisor_id", "reviewer")),
            "ranked_response_ids": ["Response A"],
            "critique": "The response makes its tradeoff explicit.",
            "missing_evidence": ["Comparable implementation cost estimates."],
        }
    return {
        "recommendation": "Use a hosted billing pilot with a clear exit plan.",
        "rationale": ["It limits delivery risk while preserving a later build decision."],
        "consensus": ["Near-term delivery risk matters."],
        "dissent": ["A custom system may provide greater long-term control."],
        "assumptions": ["The fictional product scope remains stable during the pilot."],
        "risks": ["The pilot could underrepresent integration complexity."],
        "next_actions": ["Define pilot success criteria and migration triggers."],
        "confidence": "moderate",
        "advisor_count": 5,
        "review_count": 5,
    }
