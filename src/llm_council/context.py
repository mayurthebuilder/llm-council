"""Explicit, bounded loading of private context files."""

from __future__ import annotations

from pathlib import Path

from .errors import InputError
from .security import resolve_safe_path

_ALLOWED_CONTEXT_SUFFIXES = frozenset({".md", ".txt", ".json", ".csv"})


def load_explicit_context(path: Path, root: Path, max_bytes: int = 200_000) -> str:
    """Load one explicitly named UTF-8 context file from inside ``root``."""

    if path is None:
        raise InputError("Context file is required.")

    safe_path = resolve_safe_path(path, root, must_exist=True)
    name = safe_path.name
    if safe_path.suffix.lower() not in _ALLOWED_CONTEXT_SUFFIXES:
        raise InputError(f"Context file '{name}' has an unsupported extension.")

    size = safe_path.stat().st_size
    if size > max_bytes:
        raise InputError(f"Context file '{name}' exceeds the {max_bytes}-byte limit.")

    data = safe_path.read_bytes()
    if len(data) > max_bytes:
        raise InputError(f"Context file '{name}' exceeds the {max_bytes}-byte limit.")

    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InputError(f"Context file '{name}' must be valid UTF-8.") from error
