"""Explicit, bounded loading of private context files."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .errors import InputError
from .security import redact_secrets, resolve_safe_path

_ALLOWED_CONTEXT_SUFFIXES = frozenset({".md", ".txt", ".json", ".csv"})


def load_explicit_context(path: Path, root: Path, max_bytes: int = 200_000) -> str:
    """Load one explicitly named UTF-8 context file from inside ``root``."""

    if path is None:
        raise InputError("Context file is required.")

    resolved_root = root.resolve(strict=False)
    try:
        root_details = os.stat(resolved_root, follow_symlinks=False)
    except OSError:
        raise InputError("Unable to securely access the context root.") from None

    safe_path = resolve_safe_path(path, resolved_root, must_exist=True)
    name = redact_secrets(safe_path.name or "context")
    if safe_path.suffix.lower() not in _ALLOWED_CONTEXT_SUFFIXES:
        raise InputError(f"Context file '{name}' has an unsupported extension.")

    data = _read_context_descriptor(
        safe_path,
        resolved_root,
        name,
        max_bytes,
        expected_root_identity=(root_details.st_dev, root_details.st_ino),
    )

    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise InputError(f"Context file '{name}' must be valid UTF-8.") from None


def _read_context_descriptor(
    path: Path,
    root: Path,
    name: str,
    max_bytes: int,
    *,
    expected_root_identity: tuple[int, int],
) -> bytes:
    """Read a regular file through a root-pinned, no-follow descriptor chain."""

    # The caller already resolved and identified this root. Resolving it again here
    # would follow a symlink substituted between validation and descriptor open.
    resolved_root = root
    relative = path.relative_to(resolved_root)
    root_descriptor: int | None = None
    parent_descriptor: int | None = None
    file_descriptor: int | None = None
    try:
        directory_flags = _directory_flags()
        root_descriptor = os.open(resolved_root, directory_flags)
        root_descriptor_details = os.fstat(root_descriptor)
        if (
            root_descriptor_details.st_dev,
            root_descriptor_details.st_ino,
        ) != expected_root_identity:
            raise InputError(f"Context path '{name}' changed during validation.")
        parent_descriptor = os.dup(root_descriptor)
        for component in relative.parts[:-1]:
            next_descriptor = os.open(component, directory_flags, dir_fd=parent_descriptor)
            _close_descriptor(parent_descriptor)
            parent_descriptor = next_descriptor

        file_flags = os.O_RDONLY | os.O_NOFOLLOW
        file_descriptor = os.open(relative.name, file_flags, dir_fd=parent_descriptor)
        details = os.fstat(file_descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise InputError(f"Context path '{name}' must be a regular file.")
        if details.st_size > max_bytes:
            raise InputError(f"Context file '{name}' exceeds the {max_bytes}-byte limit.")
        return _read_bounded(file_descriptor, name, max_bytes)
    except InputError:
        raise
    except (AttributeError, NotImplementedError, OSError, TypeError, ValueError):
        raise InputError(f"Unable to securely read context file '{name}'.") from None
    finally:
        if file_descriptor is not None:
            _close_descriptor(file_descriptor)
        if parent_descriptor is not None:
            _close_descriptor(parent_descriptor)
        if root_descriptor is not None:
            _close_descriptor(root_descriptor)


def _directory_flags() -> int:
    """Return required POSIX traversal flags or fail closed."""

    try:
        return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    except AttributeError:
        raise InputError("Secure context access is unavailable on this platform.") from None


def _read_bounded(file_descriptor: int, name: str, max_bytes: int) -> bytes:
    """Read at most one byte beyond the limit so concurrent growth is detected."""

    chunks: list[bytes] = []
    remaining = max_bytes + 1
    while remaining:
        chunk = os.read(file_descriptor, min(65_536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) > max_bytes:
        raise InputError(f"Context file '{name}' exceeds the {max_bytes}-byte limit.")
    return data


def _close_descriptor(descriptor: int) -> None:
    """Close without allowing cleanup failures to replace the safe domain error."""

    try:
        os.close(descriptor)
    except OSError:
        pass
