"""Optional Google Gen AI adapter behind the provider-neutral boundary."""

from __future__ import annotations

import importlib
import os
from typing import Any

from ..errors import ProviderError
from .base import CompletionRequest

DEFAULT_MODEL = "gemini-3.7-flash"


class GoogleGenAIProvider:
    """Translate provider-neutral completion requests to Google Gen AI calls."""

    def __init__(self, *, model: str = DEFAULT_MODEL) -> None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ProviderError("Google provider requires the GOOGLE_API_KEY environment variable.")

        try:
            genai: Any = importlib.import_module("google.genai")
        except ImportError:
            raise ProviderError(
                "Google provider requires the optional google dependency; install llm-council[google]."
            ) from None
        except Exception:  # noqa: BLE001 - provider SDK import errors are implementation-defined.
            raise ProviderError(
                "Google provider initialization failed. Check the optional dependency and configuration."
            ) from None

        self.model = model
        try:
            self._client: Any = genai.Client(api_key=api_key)
            self._types: Any = genai.types
        except Exception:  # noqa: BLE001 - provider SDK exception types are optional.
            raise ProviderError(
                "Google provider initialization failed. Check the optional dependency and configuration."
            ) from None

    async def complete(self, request: CompletionRequest) -> str:
        """Request JSON output and convert SDK failures into safe provider errors."""

        try:
            config = self._types.GenerateContentConfig(
                system_instruction=request.system,
                response_mime_type="application/json",
                temperature=0.2,
            )
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=request.user,
                config=config,
            )
            text = response.text
        except Exception:  # noqa: BLE001 - provider SDK exception types are optional.
            raise ProviderError(
                "Google provider request failed. Check credentials, quota, and network connection."
            ) from None

        if not isinstance(text, str) or not text:
            raise ProviderError("Google provider returned an empty completion.")
        return text

    async def aclose(self) -> None:
        """Release both async and sync transports owned by the SDK client."""

        try:
            try:
                await self._client.aio.aclose()
            finally:
                self._client.close()
        except Exception:  # noqa: BLE001 - provider SDK exception types are optional.
            raise ProviderError("Google provider cleanup failed.") from None
