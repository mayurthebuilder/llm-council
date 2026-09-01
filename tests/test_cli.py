from __future__ import annotations

import json
import socket
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

import llm_council.providers.google as google_provider
from llm_council import cli
from llm_council.errors import InputError, OutputError, ProviderError, QuorumError
from llm_council.models import CouncilDecision, CouncilRequest
from llm_council.providers.fake import DeterministicProvider

runner = CliRunner()


def test_help_describes_safe_defaults_and_explicit_run_command() -> None:
    result = runner.invoke(cli.app, ["run", "--help"], terminal_width=120)
    assert result.exit_code == 0
    help_text = " ".join(result.stdout.split())
    for option in (
        "--question", "--context-file", "--provider", "--model", "--format",
        "--output", "--overwrite", "--timeout", "--seed",
    ):
        assert option in result.stdout
    assert "demo" in result.stdout
    assert "offline" in result.stdout.lower()
    assert "GOOGLE_API_KEY" in result.stdout
    assert "gemini-3.7-flash" in result.stdout
    assert "digital marketing" in help_text.lower()
    assert "SEO" in help_text
    assert "AEO (Answer Engine Optimization)" in help_text
    assert "answer eligibility and clarity" in help_text
    assert "GEO (Generative Engine Optimization)" in help_text
    assert "generative understanding, retrieval, and citation" in help_text
    assert "not guarantee" in help_text
    root_help = " ".join(
        runner.invoke(cli.app, ["--help"], terminal_width=120).stdout.split()
    )
    assert "run" in root_help
    assert "SEO" in root_help
    assert "Answer Engine Optimization" in root_help
    assert "Generative Engine Optimization" in root_help


@pytest.mark.parametrize("provider_args", [[], ["--provider", "demo"]])
def test_demo_run_needs_no_key_or_network(
    monkeypatch: pytest.MonkeyPatch, provider_args: list[str]
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Offline run attempted a live dependency")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(google_provider.importlib, "import_module", forbidden)
    result = runner.invoke(cli.app, [
        "run", "--question", "How should a fictional B2B SaaS launch?", *provider_args,
    ])
    assert result.exit_code == 0, result.output
    assert "Recommendation" in result.stdout
    assert "fixed" in result.stderr.lower()
    assert "simulated" in result.stderr.lower()
    assert "digital marketing" in result.stderr.lower()
    assert "billing" not in result.stderr.lower()
    assert "not" in result.stderr.lower()


@pytest.mark.parametrize("format_name", ["markdown", "json", "html"])
def test_formats_keep_stdout_free_of_cli_notices(format_name: str) -> None:
    result = runner.invoke(
        cli.app,
        [
            "run", "--question", "How should a fictional B2B SaaS launch?",
            "--format", format_name,
        ],
    )
    assert result.exit_code == 0
    assert "simulated" not in result.stdout
    if format_name == "json":
        decision = CouncilDecision.model_validate_json(result.stdout)
        assert decision.advisor_count == 5
        assert decision.review_count == 5
        assert "digital marketing" in decision.recommendation.lower()
        serialized = decision.model_dump_json()
        assert all(capability in serialized for capability in ("SEO", "AEO", "GEO"))
    elif format_name == "html":
        assert result.stdout.startswith("<!doctype html>")
        assert result.stdout.rstrip().endswith("</html>")
    else:
        assert result.stdout.startswith("# Council Decision")


def test_explicit_context_timeout_and_seed_reach_real_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "context.md").write_text("Fictional brief", encoding="utf-8")
    seen: list[CouncilRequest] = []
    original_run = cli.CouncilEngine.run

    async def observe(self: Any, request: CouncilRequest) -> CouncilDecision:
        seen.append(request)
        return await original_run(self, request)

    monkeypatch.setattr(cli.CouncilEngine, "run", observe)
    result = runner.invoke(cli.app, [
        "run", "--question", "Build or buy?", "--context-file", "context.md",
        "--timeout", "1.5", "--seed", "17",
    ])
    assert result.exit_code == 0
    assert seen[0].context == "Fictional brief"
    assert seen[0].config.advisor_timeout_seconds == 1.5
    assert seen[0].config.random_seed == 17


def test_no_context_file_is_read_implicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("Context must be explicitly supplied")

    monkeypatch.setattr(cli, "load_explicit_context", forbidden)
    result = runner.invoke(cli.app, ["run", "--question", "Build or buy?"])
    assert result.exit_code == 0


def test_output_file_requires_explicit_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "decision.json"
    target.write_text("keep this", encoding="utf-8")
    args = ["run", "--question", "Build or buy?", "--format", "json", "--output", target.name]
    refused = runner.invoke(cli.app, args)
    assert refused.exit_code != 0
    assert refused.stdout == ""
    assert target.read_text() == "keep this"
    result = runner.invoke(cli.app, [*args, "--overwrite"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert CouncilDecision.model_validate_json(target.read_text()).advisor_count == 5
    assert "saved" in result.stderr.lower()


@pytest.mark.parametrize("extra", [
    ["--provider", "private-value"], ["--format", "private-value"],
    ["--timeout", "private-value"], ["--timeout", "0"], ["--timeout", "301"],
    ["--timeout", "nan"], ["--timeout", "inf"], ["--seed", "private-value"],
    ["--model", " "], ["--context-file", "private-value.md"],
    ["--output", "../private-value.json"], ["--output", "missing/decision.json"],
    ["--question", " "], ["--private-value"],
])
def test_invalid_options_fail_safely_before_google_initialization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extra: list[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Invalid options reached provider initialization")

    monkeypatch.setattr(cli, "GoogleGenAIProvider", forbidden)
    result = runner.invoke(cli.app, [
        "run", "--question", "private-question", "--provider", "google", *extra,
    ])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "Error" in result.stderr
    assert "private-value" not in result.output
    assert "private-question" not in result.output
    assert "Traceback" not in result.output
    assert not isinstance(result.exception, AssertionError)


@pytest.mark.parametrize("kind", ["existing", "directory", "symlink"])
def test_bad_output_is_rejected_before_paid_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "decision.json"
    if kind == "existing":
        target.write_text("keep")
    elif kind == "directory":
        target.mkdir()
    else:
        (tmp_path / "source").write_text("keep")
        target.symlink_to(tmp_path / "source")

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Invalid destination reached paid provider")

    monkeypatch.setattr(cli, "GoogleGenAIProvider", forbidden)
    result = runner.invoke(cli.app, [
        "run", "--question", "Build or buy?", "--provider", "google", "--output", str(target),
    ])
    assert result.exit_code != 0
    assert "Error" in result.stderr
    assert not isinstance(result.exception, AssertionError)


def test_google_missing_key_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    result = runner.invoke(cli.app, ["run", "--question", "Build or buy?", "--provider", "google"])
    assert result.exit_code != 0
    assert "GOOGLE_API_KEY" in result.stderr
    assert result.stdout == ""


def test_google_missing_extra_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "private-key")

    def missing_sdk(name: str) -> ModuleType:
        raise ImportError("private-key")

    monkeypatch.setattr(google_provider.importlib, "import_module", missing_sdk)
    result = runner.invoke(cli.app, ["run", "--question", "Build or buy?", "--provider", "google"])
    assert result.exit_code != 0
    assert "llm-council[google]" in result.stderr
    assert "private-key" not in result.output


@pytest.mark.parametrize("error_type", [InputError, OutputError, ProviderError, QuorumError])
def test_engine_failures_never_disclose_user_or_error_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error_type: type[Exception]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "context.md").write_text("private-context")
    monkeypatch.setenv("GOOGLE_API_KEY", "private-key")

    async def fail(self: Any, request: CouncilRequest) -> CouncilDecision:
        raise error_type("private-question private-context private-key")

    monkeypatch.setattr(cli.CouncilEngine, "run", fail)
    result = runner.invoke(cli.app, [
        "run", "--question", "private-question", "--context-file", "context.md",
    ])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "Error" in result.stderr
    for private in ("private-question", "private-context", "private-key", "Traceback"):
        assert private not in result.output


def test_real_engine_timeout_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "DeterministicProvider", lambda: DeterministicProvider(delay_seconds=0.1))
    result = runner.invoke(cli.app, [
        "run", "--question", "private-question", "--timeout", "0.001",
    ])
    assert result.exit_code != 0
    assert "quorum" in result.stderr.lower()
    assert "private-question" not in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("model", [None, "gemini-test-model"])
def test_google_cli_closes_clients_on_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, fails: bool, model: str | None
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "private-key")
    events: list[str] = []
    models: list[str] = []

    class FakeConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.system_instruction = kwargs["system_instruction"]

    async def generate_content(**kwargs: Any) -> SimpleNamespace:
        models.append(kwargs["model"])
        if fails:
            raise RuntimeError("private-question private-key")
        system = kwargs["config"].system_instruction
        if "independent council advisor" in system:
            payload = {
                "response_id": "draft", "analysis": "Analysis", "recommendation": "Buy",
                "assumptions": ["Scope stable"], "evidence_references": ["Brief"], "risks": ["Lock-in"],
            }
        elif "blind peer reviewer" in system:
            candidates = json.loads(kwargs["contents"].split(
                "<ANONYMOUS CANDIDATE RESPONSES>\n"
            )[1].split("\n</ANONYMOUS CANDIDATE RESPONSES>")[0])
            payload = {
                "reviewer_id": "anonymous", "ranked_response_ids": [c["response_id"] for c in candidates],
                "critique": "Plausible", "missing_evidence": ["Cost estimate"],
            }
        else:
            payload = {
                "recommendation": "Buy", "rationale": ["Speed"], "consensus": ["Delivery"],
                "dissent": ["Control"], "assumptions": ["Scope stable"], "risks": ["Lock-in"],
                "next_actions": ["Pilot"], "confidence": "moderate", "advisor_count": 5,
                "review_count": 5,
            }
        return SimpleNamespace(text=json.dumps(payload))

    async def aclose() -> None:
        events.append("async closed")

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_content), aclose=aclose,
            )

        def close(self) -> None:
            events.append("sync closed")

    sdk = SimpleNamespace(Client=FakeClient, types=SimpleNamespace(GenerateContentConfig=FakeConfig))
    monkeypatch.setattr(google_provider.importlib, "import_module", lambda name: sdk)
    extra = ["--model", model] if model else []
    result = runner.invoke(cli.app, [
        "run", "--question", "private-question", "--provider", "google", "--format", "json", *extra,
    ])
    assert result.exit_code == (1 if fails else 0), result.output
    assert events == ["async closed", "sync closed"]
    assert set(models) == {model or "gemini-3.7-flash"}
    assert "simulated" not in result.output
    assert "private-key" not in result.output
    if not fails:
        assert CouncilDecision.model_validate_json(result.stdout).recommendation == "Buy"


def test_cli_disables_rich_exception_locals() -> None:
    assert cli.app.pretty_exceptions_enable is False
