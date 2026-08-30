"""Provider-neutral request and completion protocol."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from ..models import CouncilModel, NonBlankText

CompletionPhase = Literal["advisor", "review", "chairman"]


class CompletionRequest(CouncilModel):
    """A structured prompt sent to one provider completion call."""

    phase: CompletionPhase
    system: NonBlankText
    user: NonBlankText
    metadata: dict[str, object]


@runtime_checkable
class Provider(Protocol):
    """Async boundary implemented by model-provider adapters."""

    async def complete(self, request: CompletionRequest) -> str:
        """Return one unparsed provider response for a structured prompt."""
