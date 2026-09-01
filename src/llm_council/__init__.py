"""Provider-neutral, privacy-conscious multi-advisor decision support."""

from .errors import CouncilError, InputError, OutputError, ProviderError, QuorumError
from .models import (
    DEFAULT_ADVISORS,
    AdvisorResult,
    AdvisorSpec,
    CouncilConfig,
    CouncilDecision,
    CouncilRequest,
    PeerReview,
)
from .orchestrator import CouncilEngine

__version__ = "1.0.0"

__all__ = [
    "DEFAULT_ADVISORS",
    "AdvisorResult",
    "AdvisorSpec",
    "CouncilConfig",
    "CouncilDecision",
    "CouncilEngine",
    "CouncilError",
    "CouncilRequest",
    "InputError",
    "OutputError",
    "PeerReview",
    "ProviderError",
    "QuorumError",
]
