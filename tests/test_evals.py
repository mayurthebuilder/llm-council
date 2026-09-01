from __future__ import annotations

import json
import socket
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from llm_council.models import DEFAULT_ADVISORS, CouncilRequest
from llm_council.orchestrator import CouncilEngine
from llm_council.providers.fake import DeterministicProvider

EVALUATIONS = Path(__file__).parents[1] / "evals" / "scenarios.json"
EXPECTED_SCENARIOS = {
    "b2b-saas-launch-strategy",
    "paid-organic-channel-mix",
    "campaign-positioning-creative-direction",
    "seo-aeo-geo-discoverability",
}
EXPECTED_LENS_TERMS = (
    {"brand", "audience"},
    {"growth", "channel"},
    {"seo", "aeo", "geo"},
    {"creative", "content"},
    {"measurement", "risk"},
)


def _load_scenarios() -> dict[str, Any]:
    return json.loads(EVALUATIONS.read_text(encoding="utf-8"))


def test_evaluation_fixture_is_sanitized_and_declares_its_limited_scope() -> None:
    """Removing a required case or implying outcome validation must fail the eval contract."""
    fixture = _load_scenarios()

    assert fixture["schema_version"] == 1
    scope = fixture["evaluation_scope"].lower()
    assert "deterministic" in scope
    assert "offline" in scope
    assert "structure" in scope
    for unsupported_claim in ("accuracy", "ranking", "citation", "traffic", "revenue"):
        assert unsupported_claim in scope

    scenarios = fixture["scenarios"]
    assert {scenario["id"] for scenario in scenarios} == EXPECTED_SCENARIOS
    assert all(
        set(scenario) == {"id", "title", "question", "context", "focus_areas"}
        for scenario in scenarios
    )
    assert all(scenario["question"].strip() and scenario["context"].strip() for scenario in scenarios)
    serialized = json.dumps(fixture).lower()
    assert "fictional" in serialized
    assert "@" not in serialized
    assert "/users/" not in serialized
    assert "session url" not in serialized


def test_default_roster_exposes_five_distinct_marketing_specialists() -> None:
    """A generic or incomplete roster must fail the marketing specialization evaluation."""
    assert len(DEFAULT_ADVISORS) == 5
    assert len({advisor.advisor_id for advisor in DEFAULT_ADVISORS}) == 5
    roster_text = [f"{advisor.lens} {advisor.instructions}".lower() for advisor in DEFAULT_ADVISORS]
    for required_terms in EXPECTED_LENS_TERMS:
        assert any(required_terms <= set(text.replace(",", "").split()) for text in roster_text)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_id", sorted(EXPECTED_SCENARIOS))
async def test_scenario_runs_offline_and_returns_bounded_structured_decision(
    scenario_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Network use or loss of required decision sections must fail every offline scenario."""

    def forbid_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Deterministic evaluation attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    scenario = next(
        item for item in _load_scenarios()["scenarios"] if item["id"] == scenario_id
    )
    provider = DeterministicProvider()
    decision = await CouncilEngine(provider).run(
        CouncilRequest(question=scenario["question"], context=scenario["context"])
    )

    phases = Counter(item.request.phase for item in provider.request_timestamps)
    assert phases == {"advisor": 5, "review": 5, "chairman": 1}
    assert decision.advisor_count == 5
    assert decision.review_count == 5
    assert decision.confidence in {"low", "moderate", "high"}
    for section in (
        decision.rationale,
        decision.consensus,
        decision.dissent,
        decision.assumptions,
        decision.risks,
        decision.next_actions,
    ):
        assert section

    serialized = decision.model_dump_json().lower()
    assert all(term in serialized for term in ("seo", "aeo", "geo"))
    assert "evidence" in serialized
    assert "cannot guarantee" in serialized
    assert all(term in serialized for term in ("rankings", "citations", "traffic", "revenue"))

    advisor_requests = [
        item.request for item in provider.request_timestamps if item.request.phase == "advisor"
    ]
    supplied_context = {request.user for request in advisor_requests}
    assert len(supplied_context) == 1
    assert scenario["question"] in supplied_context.pop()
