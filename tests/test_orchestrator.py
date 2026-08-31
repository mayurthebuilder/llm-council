from __future__ import annotations

import asyncio
import json
import traceback
from collections.abc import Callable
from time import monotonic

import pytest

from llm_council.errors import InputError, ProviderError, QuorumError
from llm_council.models import (
    DEFAULT_ADVISORS,
    AdvisorSpec,
    CouncilConfig,
    CouncilRequest,
    PeerReview,
)
from llm_council.orchestrator import CouncilEngine
from llm_council.prompts import build_chairman_request
from llm_council.providers.base import CompletionRequest
from llm_council.providers.fake import DeterministicProvider

SECRET = "private-key-and-provider-response"


class FaultProvider:
    """Alter only the completion boundary; run real prompts, parsing and fake payloads."""

    def __init__(
        self,
        *,
        failures: set[tuple[str, int]] | None = None,
        timeouts: set[tuple[str, int]] | None = None,
        invalid_json: set[tuple[str, int]] | None = None,
        mutate: Callable[[CompletionRequest, dict[str, object], int], None] | None = None,
    ) -> None:
        self.fake = DeterministicProvider()
        self.failures = failures or set()
        self.timeouts = timeouts or set()
        self.invalid_json = invalid_json or set()
        self.mutate = mutate
        self.requests: list[CompletionRequest] = []
        self.counts: dict[str, int] = {}
        self.cancelled = 0

    async def complete(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        index = self.counts.get(request.phase, 0)
        self.counts[request.phase] = index + 1
        key = (request.phase, index)
        if key in self.failures:
            raise RuntimeError(SECRET)
        if key in self.timeouts:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
        if key in self.invalid_json:
            return SECRET
        payload = json.loads(await self.fake.complete(request))
        if self.mutate is not None:
            self.mutate(request, payload, index)
        return json.dumps(payload)


def _question(config: CouncilConfig | None = None) -> CouncilRequest:
    return CouncilRequest(
        question="Should the fictional team build or buy billing?",
        config=config or CouncilConfig(random_seed=7),
    )


@pytest.mark.asyncio
async def test_runs_five_advisors_reviews_and_chairman() -> None:
    """Dropping either deliberation stage must change the final execution counts."""
    provider = DeterministicProvider(delay_seconds=0.01)
    decision = await CouncilEngine(provider).run(_question())
    assert decision.advisor_count == 5
    assert decision.review_count == 5
    assert decision.recommendation
    assert decision.dissent
    assert [record.request.phase for record in provider.request_timestamps] == (
        ["advisor"] * 5 + ["review"] * 5 + ["chairman"]
    )


@pytest.mark.asyncio
async def test_advisors_and_reviews_execute_concurrently() -> None:
    """Sequential provider calls exceed the allowed stage duration."""
    delay = 0.06
    provider = DeterministicProvider(delay_seconds=delay)
    await CouncilEngine(provider).run(_question())
    for phase in ("advisor", "review"):
        timings = [t for t in provider.request_timestamps if t.request.phase == phase]
        elapsed = max(t.completed_at for t in timings) - min(t.started_at for t in timings)
        assert elapsed < 5 * delay * 0.6
        assert max(t.started_at for t in timings) < min(t.completed_at for t in timings)


@pytest.mark.asyncio
async def test_reviews_exclude_self_and_replace_untrusted_ids_reproducibly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model identities and self-responses must never enter a review candidate list."""

    def identify(request: CompletionRequest, payload: dict[str, object], index: int) -> None:
        if request.phase == "advisor":
            payload["response_id"] = SECRET  # Deliberately identical untrusted IDs.
            payload["analysis"] = f"Distinct analysis {index}"
        if request.phase == "review":
            payload["reviewer_id"] = SECRET

    observed_reviews: list[PeerReview] = []

    def capture_reviews(request, results, reviews):
        observed_reviews.extend(reviews)
        return build_chairman_request(request, results, reviews)

    monkeypatch.setattr("llm_council.orchestrator.build_chairman_request", capture_reviews)
    runs: list[list[str]] = []
    for seed in (7, 7, 19):
        provider = FaultProvider(mutate=identify)
        await CouncilEngine(provider).run(_question(CouncilConfig(random_seed=seed)))
        reviews = [r for r in provider.requests if r.phase == "review"]
        assert len(reviews) == 5
        for index, review in enumerate(reviews):
            assert f"Distinct analysis {index}" not in review.user
            assert len(review.metadata["candidate_response_ids"]) == 4
            serialized = review.model_dump_json()
            assert SECRET not in serialized
            assert all(spec.advisor_id not in serialized for spec in DEFAULT_ADVISORS)
        chairman = next(r for r in provider.requests if r.phase == "chairman")
        assert SECRET not in chairman.model_dump_json()
        runs.append([r.user for r in reviews])
    assert runs[0] == runs[1]
    assert runs[0] != runs[2]
    assert len(observed_reviews) == 15
    for review in observed_reviews:
        assert review.reviewer_id in {f"Response {letter}" for letter in "ABCDE"}
        assert review.reviewer_id not in review.ranked_response_ids


@pytest.mark.asyncio
async def test_three_advisors_continue_with_actual_counts_and_safe_metadata() -> None:
    """Model-claimed execution counts and metadata cannot override local outcomes."""

    def lie(request: CompletionRequest, payload: dict[str, object], _: int) -> None:
        if request.phase == "chairman":
            payload.update(advisor_count=5, review_count=5, execution_metadata={SECRET: 999})

    provider = FaultProvider(failures={("advisor", 0), ("advisor", 1)}, mutate=lie)
    decision = await CouncilEngine(provider).run(_question())
    assert (decision.advisor_count, decision.review_count) == (3, 3)
    assert decision.execution_metadata["advisor_failures"] == 2
    assert decision.execution_metadata["review_failures"] == 0
    assert decision.execution_metadata["duration_seconds"] > 0
    assert all(type(value) in (int, float) for value in decision.execution_metadata.values())
    assert SECRET not in decision.model_dump_json()
    chairman = next(r for r in provider.requests if r.phase == "chairman")
    assert chairman.metadata == {"advisor_count": 3, "review_count": 3}


@pytest.mark.asyncio
@pytest.mark.parametrize("phase,count", [("advisor", 3), ("review", 4)])
@pytest.mark.parametrize("fault", ["failures", "invalid_json"])
async def test_quorum_failure_is_safe_and_prevents_later_phases(
    phase: str, count: int, fault: str
) -> None:
    """Too few valid outputs must stop synthesis, without exposing provider failures."""
    provider = FaultProvider(**{fault: {(phase, index) for index in range(count)}})
    with pytest.raises(QuorumError) as caught:
        await CouncilEngine(provider).run(_question())
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    assert "chairman" not in provider.counts
    if phase == "advisor":
        assert "review" not in provider.counts


@pytest.mark.asyncio
async def test_per_call_timeouts_are_cancelled_and_counted() -> None:
    """An overdue completion must be cancelled while healthy peers continue."""
    provider = FaultProvider(timeouts={("advisor", 0), ("review", 0)})
    started = monotonic()
    decision = await CouncilEngine(provider).run(
        _question(CouncilConfig(advisor_timeout_seconds=0.03))
    )
    assert monotonic() - started < 0.5
    assert (decision.advisor_count, decision.review_count) == (4, 3)
    assert provider.cancelled == 2
    assert decision.execution_metadata["advisor_timeouts"] == 1
    assert decision.execution_metadata["review_timeouts"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["failures", "invalid_json", "timeouts"])
async def test_chairman_failure_is_safe_and_returns_no_partial_decision(fault: str) -> None:
    """Synthesis failure cannot leak raw provider text or masquerade as a decision."""
    provider = FaultProvider(**{fault: {("chairman", 0)}})
    with pytest.raises(ProviderError) as caught:
        await CouncilEngine(provider).run(_question(CouncilConfig(advisor_timeout_seconds=0.02)))
    assert SECRET not in "".join(traceback.format_exception(caught.value))


@pytest.mark.asyncio
@pytest.mark.parametrize("ranking", ["duplicate", "foreign", "self"])
async def test_invalid_review_rankings_do_not_count_toward_quorum(ranking: str) -> None:
    """Duplicates, invented IDs and a reviewer's own label are invalid votes."""

    def corrupt(request: CompletionRequest, payload: dict[str, object], _: int) -> None:
        if request.phase == "review":
            candidates = request.metadata["candidate_response_ids"]
            if ranking == "duplicate":
                payload["ranked_response_ids"] = [candidates[0], candidates[0]]
            elif ranking == "foreign":
                payload["ranked_response_ids"] = ["invented-response"]
            else:
                all_labels = {f"Response {letter}" for letter in "ABCDE"}
                payload["ranked_response_ids"] = list(all_labels - set(candidates))

    provider = FaultProvider(mutate=corrupt)
    with pytest.raises(QuorumError):
        await CouncilEngine(provider).run(_question())
    assert "chairman" not in provider.counts


@pytest.mark.asyncio
async def test_config_precedence_and_separate_chairman_provider() -> None:
    """The request config is effective unless the engine explicitly overrides it."""
    request = _question(CouncilConfig(min_advisors=5))
    provider = FaultProvider(failures={("advisor", 0)})
    with pytest.raises(QuorumError):
        await CouncilEngine(provider).run(request)
    provider = FaultProvider(failures={("advisor", 0)})
    chairman = DeterministicProvider()
    decision = await CouncilEngine(provider, CouncilConfig(min_advisors=3), chairman).run(request)
    assert decision.advisor_count == 4
    assert "chairman" not in provider.counts
    assert [t.request.phase for t in chairman.request_timestamps] == ["chairman"]


@pytest.mark.asyncio
async def test_custom_five_advisors_are_used_and_must_have_unique_ids() -> None:
    """Custom lenses must reach advisor prompts, but invalid rosters must fail early."""
    advisors = tuple(
        AdvisorSpec(advisor_id=f"custom-{index}", lens=f"custom lens {index}") for index in range(5)
    )
    provider = DeterministicProvider()
    await CouncilEngine(provider, advisors=advisors).run(_question())
    requests = [t.request for t in provider.request_timestamps if t.request.phase == "advisor"]
    assert {r.metadata["advisor_id"] for r in requests} == {a.advisor_id for a in advisors}
    assert all(advisor.lens in request.system for advisor, request in zip(advisors, requests))
    for invalid in ((), advisors[:4], advisors + advisors[:1], (advisors[0],) * 5):
        with pytest.raises(InputError):
            CouncilEngine(provider, advisors=invalid)


@pytest.mark.asyncio
async def test_one_advisor_can_synthesize_without_self_review_when_configured() -> None:
    """A zero-review quorum must not force an impossible self-review."""
    provider = FaultProvider(failures={("advisor", index) for index in range(4)})
    decision = await CouncilEngine(provider).run(
        _question(CouncilConfig(min_advisors=1, min_reviews=0))
    )
    assert (decision.advisor_count, decision.review_count) == (1, 0)
    assert "review" not in provider.counts


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["advisor", "review", "chairman"])
async def test_cancellation_propagates_and_cancels_inflight_work(phase: str) -> None:
    """Cancelling a run must not be swallowed as an ordinary quorum failure."""
    call_count = 1 if phase == "chairman" else 5
    provider = FaultProvider(timeouts={(phase, index) for index in range(call_count)})
    task = asyncio.create_task(CouncilEngine(provider).run(_question()))
    async with asyncio.timeout(1):
        while provider.counts.get(phase, 0) < call_count:
            await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.cancelled == call_count
    if phase == "advisor":
        assert "review" not in provider.counts
    if phase != "chairman":
        assert "chairman" not in provider.counts


@pytest.mark.asyncio
async def test_provider_cancellation_propagates_instead_of_becoming_a_failure_count() -> None:
    """A provider's cancellation is control flow even when gather returns it as an outcome."""

    def cancel(request: CompletionRequest, _: dict[str, object], index: int) -> None:
        if request.phase == "advisor" and index == 0:
            raise asyncio.CancelledError

    provider = FaultProvider(mutate=cancel)
    with pytest.raises(asyncio.CancelledError):
        await CouncilEngine(provider).run(_question())
    assert "review" not in provider.counts


@pytest.mark.asyncio
async def test_two_valid_reviews_meet_default_review_quorum() -> None:
    """The exact configured review quorum succeeds, without counting failed peers."""
    provider = FaultProvider(failures={("review", index) for index in range(3)})
    decision = await CouncilEngine(provider).run(_question())
    assert decision.review_count == 2
    assert decision.execution_metadata["review_failures"] == 3


@pytest.mark.asyncio
async def test_malformed_chairman_counts_are_not_repaired_before_strict_parsing() -> None:
    """Local accounting overrides valid claims but does not bypass schema validation."""

    def corrupt(request: CompletionRequest, payload: dict[str, object], _: int) -> None:
        if request.phase == "chairman":
            payload["advisor_count"] = 999

    with pytest.raises(ProviderError):
        await CouncilEngine(FaultProvider(mutate=corrupt)).run(_question())
