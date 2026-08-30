from __future__ import annotations

from pathlib import Path

import pytest

from llm_council.errors import InputError, OutputError
from llm_council.security import redact_secrets, resolve_safe_path


def test_redacts_assignment_and_google_shaped_key() -> None:
    value = "token=super-secret-value AIzaabcdefghijklmnopqrstuvwxyz123456"

    redacted = redact_secrets(value)

    assert "super-secret-value" not in redacted
    assert "AIza" not in redacted
    assert redacted.count("[REDACTED]") == 2


def test_rejects_path_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()

    with pytest.raises(InputError, match="inside the working directory"):
        resolve_safe_path(root / ".." / "private.txt", root, must_exist=False)


def test_rejects_symlink_even_when_target_is_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "actual.md"
    target.write_text("safe context", encoding="utf-8")
    alias = root / "alias.md"
    alias.symlink_to(target)

    with pytest.raises(InputError, match="alias.md"):
        resolve_safe_path(alias, root, must_exist=True)


def test_returns_resolved_existing_file_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "nested" / "context.md"
    context.parent.mkdir()
    context.write_text("safe context", encoding="utf-8")

    assert resolve_safe_path(context, root, must_exist=True) == context.resolve()


def test_rejects_directory_as_an_output_path(tmp_path: Path) -> None:
    root = tmp_path / "project"
    output_directory = root / "reports"
    output_directory.mkdir(parents=True)

    with pytest.raises(OutputError, match="reports"):
        resolve_safe_path(output_directory, root, must_exist=False)
