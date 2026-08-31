"""Concurrent, identity-blind council deliberation with explicit quorum gates."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Mapping, Sequence
from time import monotonic
from typing import TypeVar

from .errors import InputError, ProviderError, QuorumError
from .models import (
    DEFAULT_ADVISORS,
    AdvisorResult,
    AdvisorSpec,
    CouncilConfig,
    CouncilDecision,
    CouncilModel,
    CouncilRequest,
    PeerReview,
)
from .parsing import parse_model
from .prompts import build_advisor_request, build_chairman_request, build_review_request
from .providers.base import CompletionRequest, Provider

T = TypeVar("T", bound=CouncilModel)


class CouncilEngine:
    """Run five advisors, blind peer review and chairman synthesis.

    An explicit engine config overrides the request config. Otherwise each run
    uses its own request settings, including timeout, quorums and random seed.
    """

    def __init__(
        self,
        provider: Provider,
        config: CouncilConfig | None = None,
        chairman: Provider | None = None,
        *,
        advisors: Sequence[AdvisorSpec] | None = None,
    ) -> None:
        roster = tuple(DEFAULT_ADVISORS if advisors is None else advisors)
        if (
            len(roster) != 5
            or any(not isinstance(spec, AdvisorSpec) for spec in roster)
            or len({spec.advisor_id for spec in roster}) != 5
        ):
            raise InputError("The council requires exactly five advisors with unique IDs.")
        self.provider = provider
        self.config = config
        self.chairman = provider if chairman is None else chairman
        self.advisors = roster

    async def run(self, request: CouncilRequest) -> CouncilDecision:
        """Return a complete decision, or a safe error without partial output."""
        started_at = monotonic()
        config = self.config if self.config is not None else request.config
        timeout = config.advisor_timeout_seconds
        labels = [f"Response {letter}" for letter in "ABCDE"]
        random.Random(config.random_seed).shuffle(labels)
        identities = {spec.advisor_id: label for spec, label in zip(self.advisors, labels)}

        advisor_calls = {
            spec.advisor_id: build_advisor_request(request, spec) for spec in self.advisors
        }
        advisors, advisor_failures, advisor_timeouts = await _complete_stage(
            self.provider, advisor_calls, AdvisorResult, timeout
        )
        advisor_duration = monotonic() - started_at
        if len(advisors) < config.min_advisors:
            raise QuorumError(
                f"Advisor quorum not met: {len(advisors)} of {config.min_advisors} required."
            ) from None

        # Only locally assigned labels cross into review and synthesis prompts.
        results = {
            identities[advisor_id]: result.model_copy(
                update={"response_id": identities[advisor_id]}
            )
            for advisor_id, result in advisors.items()
        }
        review_started_at = monotonic()
        review_calls: dict[str, CompletionRequest] = {}
        candidate_ids: dict[str, set[str]] = {}
        for reviewer_id in results:
            candidates = {
                label: result for label, result in results.items() if label != reviewer_id
            }
            if candidates:
                review_calls[reviewer_id] = build_review_request(request, candidates)
                candidate_ids[reviewer_id] = set(candidates)
        parsed_reviews, review_failures, review_timeouts = await _complete_stage(
            self.provider, review_calls, PeerReview, timeout
        )
        reviews: list[PeerReview] = []
        for reviewer_id, review in parsed_reviews.items():
            rankings = review.ranked_response_ids
            if (
                len(rankings) != len(set(rankings))
                or not set(rankings) <= candidate_ids[reviewer_id]
            ):
                review_failures += 1
                continue
            reviews.append(review.model_copy(update={"reviewer_id": reviewer_id}))
        review_duration = monotonic() - review_started_at
        if len(reviews) < config.min_reviews:
            raise QuorumError(
                f"Review quorum not met: {len(reviews)} of {config.min_reviews} required."
            ) from None

        chairman_started_at = monotonic()
        try:
            decision = await asyncio.wait_for(
                _complete_model(
                    self.chairman,
                    build_chairman_request(request, results, reviews),
                    CouncilDecision,
                ),
                timeout=timeout,
            )
        except Exception:  # noqa: BLE001 - provider exception types are implementation-defined.
            raise ProviderError("Chairman synthesis failed; no decision was produced.") from None

        # Never trust provider-supplied counts or arbitrary execution metadata.
        return decision.model_copy(
            update={
                "advisor_count": len(results),
                "review_count": len(reviews),
                "execution_metadata": {
                    "advisor_failures": advisor_failures,
                    "review_failures": review_failures,
                    "advisor_timeouts": advisor_timeouts,
                    "review_timeouts": review_timeouts,
                    "advisor_duration_seconds": advisor_duration,
                    "review_duration_seconds": review_duration,
                    "chairman_duration_seconds": monotonic() - chairman_started_at,
                    "duration_seconds": monotonic() - started_at,
                },
            }
        )


async def _complete_model(provider: Provider, request: CompletionRequest, model_type: type[T]) -> T:
    """Keep provider output internal and return only strictly validated models."""
    return parse_model(await provider.complete(request), model_type)


async def _complete_stage(
    provider: Provider,
    requests: Mapping[str, CompletionRequest],
    model_type: type[T],
    timeout: float,
) -> tuple[dict[str, T], int, int]:
    """Complete a stage concurrently, retaining only valid results and numeric stats."""
    outcomes = await asyncio.gather(
        *(
            asyncio.wait_for(_complete_model(provider, request, model_type), timeout=timeout)
            for request in requests.values()
        ),
        return_exceptions=True,
    )
    results: dict[str, T] = {}
    failures = 0
    timeouts = 0
    for identifier, outcome in zip(requests, outcomes):
        if isinstance(outcome, BaseException):
            if not isinstance(outcome, Exception):
                # Cancellation is control flow, not a provider/quorum failure.
                raise outcome
            failures += 1
            timeouts += int(isinstance(outcome, TimeoutError))
        else:
            results[identifier] = outcome
    return results, failures, timeouts
