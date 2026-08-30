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
    resolved_path = supplied_path.resolve(strict=False)
    name = _safe_basename(path)

    if not resolved_path.is_relative_to(resolved_root):
        raise InputError(f"Path '{name}' must be inside the working directory.")

    _reject_symlink_components(supplied_path, resolved_root, name)

    if must_exist:
        if not resolved_path.exists():
            raise InputError(f"Input file '{name}' does not exist.")
        if not resolved_path.is_file():
            raise InputError(f"Input path '{name}' must be a file.")
    elif resolved_path.exists() and resolved_path.is_dir():
        raise OutputError(f"Output path '{name}' must name a file.")

    return resolved_path


def _reject_symlink_components(path: Path, root: Path, name: str) -> None:
    """Reject a supplied leaf or ancestor symlink below the resolved root."""

    try:
        relative_path = path.relative_to(root)
    except ValueError:
        return

    current = root
    for component in relative_path.parts:
        current = current / component
        if current.is_symlink():
            raise InputError(f"Path '{name}' must not be a symlink.")


def _safe_basename(path: Path) -> str:
    """Return the only file identifier that may appear in user-facing errors."""

    return path.name or "context"
