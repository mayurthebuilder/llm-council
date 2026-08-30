"""Boundary checks for explicit files and sensitive values."""

from __future__ import annotations

import re
from pathlib import Path

from .errors import InputError, OutputError

_ASSIGNMENT_SECRET_PATTERN = re.compile(
    r"\b(api_key|token|secret|password)\b\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)
_GOOGLE_API_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_-]+")


def redact_secrets(value: str) -> str:
    """Replace common credential values with a fixed safe marker."""

    redacted = _ASSIGNMENT_SECRET_PATTERN.sub(r"\1=[REDACTED]", value)
    return _GOOGLE_API_KEY_PATTERN.sub("[REDACTED]", redacted)


def resolve_safe_path(path: Path, root: Path, *, must_exist: bool) -> Path:
    """Resolve a file path only when it stays inside ``root`` without symlinks."""

    resolved_root = root.resolve(strict=False)
    supplied_path = path if path.is_absolute() else resolved_root / path
    name = _safe_basename(path)
    error_type = InputError if must_exist else OutputError

    _reject_symlink_components(supplied_path, name, error_type)

    resolved_path = supplied_path.resolve(strict=False)

    if not resolved_path.is_relative_to(resolved_root):
        raise error_type(f"Path '{name}' must be inside the working directory.")

    if must_exist:
        if not resolved_path.exists():
            raise InputError(f"Input file '{name}' does not exist.")
        if not resolved_path.is_file():
            raise InputError(f"Input path '{name}' must be a file.")
    elif resolved_path.exists() and resolved_path.is_dir():
        raise OutputError(f"Output path '{name}' must name a file.")

    return resolved_path


def _reject_symlink_components(
    path: Path, name: str, error_type: type[InputError | OutputError]
) -> None:
    """Reject every symlink component in the supplied path before resolution."""

    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        if current.is_symlink():
            raise error_type(f"Path '{name}' must not be a symlink.")


def _safe_basename(path: Path) -> str:
    """Return the only file identifier that may appear in user-facing errors."""

    return redact_secrets(path.name or "context")
