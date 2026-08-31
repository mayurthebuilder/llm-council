from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import llm_council.providers.google as google_provider
from llm_council.errors import ProviderError
from llm_council.providers.base import CompletionRequest
from llm_council.providers.google import GoogleGenAIProvider


def _request() -> CompletionRequest:
    return CompletionRequest(
        phase="advisor",
        system="Return only JSON.",
        user="A fictional billing decision.",
        metadata={"advisor_id": "advisor-1"},
    )


def _install_fake_google(monkeypatch: pytest.MonkeyPatch, *, response_text: str = '{"ok": true}') -> Any:
    calls: dict[str, Any] = {}

    class FakeConfig:
        def __init__(self, **kwargs: Any) -> None:
            calls["config"] = kwargs

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            calls["api_key"] = api_key
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=self.generate_content)
            )

        async def generate_content(self, **kwargs: Any) -> SimpleNamespace:
            calls["request"] = kwargs
            return SimpleNamespace(text=response_text)

    genai = ModuleType("google.genai")
    genai.Client = FakeClient  # type: ignore[attr-defined]
    genai.types = SimpleNamespace(GenerateContentConfig=FakeConfig)  # type: ignore[attr-defined]
    google = ModuleType("google")
    google.genai = genai  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    return calls


def test_google_adapter_module_does_not_import_optional_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """An eager SDK import would break the default package installation."""

    monkeypatch.delitem(sys.modules, "google.genai", raising=False)
    monkeypatch.delitem(sys.modules, "google", raising=False)

    importlib.reload(google_provider)

    assert "google.genai" not in sys.modules


@pytest.mark.asyncio
async def test_google_adapter_lazily_imports_sdk_and_forwards_json_configuration(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed SDK boundary must preserve the provider-neutral JSON contract."""

    monkeypatch.setenv("GOOGLE_API_KEY", "unit-test-key")
    calls = _install_fake_google(monkeypatch)
    environment_reads: list[str] = []

    def getenv(name: str, default: str | None = None) -> str | None:
        environment_reads.append(name)
        return "unit-test-key" if name == "GOOGLE_API_KEY" else default

    monkeypatch.setattr(google_provider.os, "getenv", getenv)

    provider = GoogleGenAIProvider()
    response = await provider.complete(_request())

    assert response == '{"ok": true}'
    assert environment_reads == ["GOOGLE_API_KEY"]
    assert calls["api_key"] == "unit-test-key"
    assert calls["request"]["model"] == "gemini-3.7-flash"
    assert calls["request"]["contents"] == "A fictional billing decision."
    assert calls["config"] == {
        "system_instruction": "Return only JSON.",
        "response_mime_type": "application/json",
        "temperature": 0.2,
    }


def test_google_adapter_uses_explicit_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignoring a caller-selected model would make the CLI override ineffective."""

    monkeypatch.setenv("GOOGLE_API_KEY", "unit-test-key")
    _install_fake_google(monkeypatch)

    assert GoogleGenAIProvider(model="gemini-test-model").model == "gemini-test-model"


def test_google_adapter_rejects_missing_key_without_exposing_environment_values(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing credential must be actionable without leaking other environment data."""

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("UNRELATED_SECRET", "token=unit-test-secret")

    with pytest.raises(ProviderError) as error:
        GoogleGenAIProvider()

    assert "GOOGLE_API_KEY" in str(error.value)
    assert "unit-test-secret" not in str(error.value)


def test_google_adapter_converts_sdk_import_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-ImportError SDK loader failure must not escape with credential text."""

    monkeypatch.setenv("GOOGLE_API_KEY", "unit-test-key")

    def fail_import(name: str) -> ModuleType:
        raise RuntimeError(f"cannot import {name}: token=unit-test-secret")

    monkeypatch.setattr(google_provider.importlib, "import_module", fail_import)

    with pytest.raises(ProviderError) as error:
        GoogleGenAIProvider()

    assert "unit-test-secret" not in str(error.value)
    assert "token=" not in str(error.value)
    assert "Google provider initialization failed" in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


def test_google_adapter_redacts_sdk_initialization_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A credential-shaped SDK initialization error must not escape unchanged."""

    monkeypatch.setenv("GOOGLE_API_KEY", "unit-test-key")
    _install_fake_google(monkeypatch)

    def fail_client(*, api_key: str) -> None:
        raise RuntimeError("authentication failed token=unit-test-secret")

    genai = sys.modules["google.genai"]
    monkeypatch.setattr(genai, "Client", fail_client)

    with pytest.raises(ProviderError) as error:
        GoogleGenAIProvider()

    assert "unit-test-secret" not in str(error.value)
    assert "token=" not in str(error.value)
    assert "Google provider initialization failed" in str(error.value)


@pytest.mark.asyncio
async def test_google_adapter_converts_configuration_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK configuration construction must stay inside the safe provider boundary."""

    monkeypatch.setenv("GOOGLE_API_KEY", "unit-test-key")
    _install_fake_google(monkeypatch)

    class FailingConfig:
        def __init__(self, **kwargs: Any) -> None:
            raise RuntimeError("invalid configuration token=unit-test-secret")

    genai = sys.modules["google.genai"]
    monkeypatch.setattr(genai.types, "GenerateContentConfig", FailingConfig)

    with pytest.raises(ProviderError) as error:
        await GoogleGenAIProvider().complete(_request())

    assert "unit-test-secret" not in str(error.value)
    assert "token=" not in str(error.value)
    assert "Google provider request failed" in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


@pytest.mark.asyncio
async def test_google_adapter_redacts_sdk_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raw SDK failures must not disclose credentials through the public exception."""

    monkeypatch.setenv("GOOGLE_API_KEY", "unit-test-key")
    calls = _install_fake_google(monkeypatch)

    async def fail_request(**kwargs: Any) -> SimpleNamespace:
        calls["request"] = kwargs
        raise RuntimeError("rate limit rejected token=unit-test-secret")

    provider = GoogleGenAIProvider()
    provider._client.aio.models.generate_content = fail_request

    with pytest.raises(ProviderError) as error:
        await provider.complete(_request())

    assert "unit-test-secret" not in str(error.value)
    assert "token=" not in str(error.value)
    assert "Google provider request failed" in str(error.value)


@pytest.mark.asyncio
async def test_google_adapter_converts_response_text_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An SDK response property failure must not expose its raw diagnostic text."""

    monkeypatch.setenv("GOOGLE_API_KEY", "unit-test-key")
    _install_fake_google(monkeypatch)

    class FailingResponse:
        @property
        def text(self) -> str:
            raise RuntimeError("response decoding token=unit-test-secret")

    async def return_failing_response(**kwargs: Any) -> FailingResponse:
        return FailingResponse()

    provider = GoogleGenAIProvider()
    provider._client.aio.models.generate_content = return_failing_response

    with pytest.raises(ProviderError) as error:
        await provider.complete(_request())

    assert "unit-test-secret" not in str(error.value)
    assert "token=" not in str(error.value)
    assert "Google provider request failed" in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__
