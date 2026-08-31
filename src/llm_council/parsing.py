"""Strict, safe parsing for structured model responses."""

from __future__ import annotations

import json
import re
from typing import NoReturn, TypeVar

from pydantic import ValidationError

from .errors import OutputError
from .models import CouncilModel

T = TypeVar("T", bound=CouncilModel)

_MAX_MODEL_OUTPUT_CHARS = 1_000_000
_JSON_FENCE = re.compile(r"\A```json[ \t]*\r?\n(?P<body>.*)\r?\n?```\Z", re.DOTALL | re.IGNORECASE)


def parse_model(text: str, model_type: type[T]) -> T:
    """Parse one JSON object into a validated council model without exposing raw output."""

    if len(text) > _MAX_MODEL_OUTPUT_CHARS:
        raise OutputError("Model output exceeds the permitted size.") from None

    candidate = _strip_json_fence(text)
    try:
        payload = json.loads(candidate, parse_constant=_reject_nonfinite_constant)
    except ValueError:
        raise OutputError("Model output must be a valid JSON object.") from None

    if not isinstance(payload, dict):
        raise OutputError("Model output must be a JSON object.") from None

    try:
        return model_type.model_validate(payload)
    except ValidationError:
        raise OutputError("Model output does not match the required schema.") from None


def _strip_json_fence(text: str) -> str:
    """Remove at most one complete Markdown JSON fence, without repairing its body."""

    candidate = text.strip()
    match = _JSON_FENCE.fullmatch(candidate)
    return match.group("body") if match else candidate


def _reject_nonfinite_constant(_: str) -> NoReturn:
    """Reject JSON extensions such as NaN and Infinity before model validation."""

    raise ValueError("Non-finite JSON constants are not permitted.")
