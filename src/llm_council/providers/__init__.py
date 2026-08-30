"""Provider-neutral completion boundaries and built-in adapters."""

from .base import CompletionRequest, Provider
from .fake import DeterministicProvider
from .google import GoogleGenAIProvider

__all__ = [
    "CompletionRequest",
    "DeterministicProvider",
    "GoogleGenAIProvider",
    "Provider",
]
