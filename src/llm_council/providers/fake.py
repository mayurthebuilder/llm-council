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
            "response_id": "draft-response",
            "analysis": (
                "A staged digital marketing launch can connect audience positioning, "
                "channel tests, and trustworthy discoverable content."
            ),
            "recommendation": (
                "Run a measured 90-day digital marketing launch before scaling spend."
            ),
            "assumptions": ["The fictional team can support one focused launch segment."],
            "evidence_references": ["Only the supplied fictional marketing brief."],
            "risks": ["Audience and channel assumptions lack current performance evidence."],
        }
    if request.phase == "review":
        return {
            "reviewer_id": str(request.metadata.get("advisor_id", "reviewer")),
            "ranked_response_ids": request.metadata.get("candidate_response_ids", ["Response A"]),
            "critique": "The response proposes a bounded digital marketing test.",
            "missing_evidence": ["Current search demand, channel benchmarks, and customer research."],
        }
    return {
        "recommendation": (
            "Run a 90-day digital marketing launch for one B2B segment, pairing SEO "
            "foundations with testable AEO and GEO content practices."
        ),
        "rationale": [
            "A bounded launch links positioning, content, channels, and measurement before scaling."
        ],
        "consensus": [
            (
                "Use people-first original evidence, clear entity information, crawlable pages, "
                "and concise answer-first content."
            )
        ],
        "dissent": [
            (
                "Paid acquisition may accelerate learning, but its budget share should depend on "
                "observed lead quality and conversion data."
            )
        ],
        "assumptions": ["The fictional company has no verified baseline for qualified demand."],
        "risks": [
            "SEO, AEO, and GEO tactics cannot guarantee rankings, citations, traffic, or revenue."
        ],
        "next_actions": [
            (
                "Validate the audience, publish one evidence-led topic cluster, define "
                "qualified-demand KPIs, and run instrumented channel experiments."
            )
        ],
        "confidence": "moderate",
        "advisor_count": request.metadata.get("advisor_count", 5),
        "review_count": request.metadata.get("review_count", 5),
    }
