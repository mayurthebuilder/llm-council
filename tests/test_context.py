from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from llm_council import context as context_module
from llm_council.context import load_explicit_context
from llm_council.errors import InputError


def test_loads_explicit_markdown_context_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "brief.md"
    context.write_text("# Decision brief\n\nUse only supplied facts.", encoding="utf-8")

    assert load_explicit_context(context, root) == "# Decision brief\n\nUse only supplied facts."


def test_loads_explicit_context_from_nested_directory(tmp_path: Path) -> None:
    root = tmp_path / "project"
    nested = root / "briefs"
    nested.mkdir(parents=True)
    context = nested / "launch.md"
    context.write_text("approved nested brief", encoding="utf-8")

    assert load_explicit_context(context, root) == "approved nested brief"


def test_rejects_omitted_context_path(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()

    with pytest.raises(InputError, match="Context file is required"):
        load_explicit_context(None, root)  # type: ignore[arg-type]


def test_rejects_directory_context_using_only_its_basename(tmp_path: Path) -> None:
    root = tmp_path / "project"
    directory = root / "context.md"
    directory.mkdir(parents=True)

    with pytest.raises(InputError) as error:
        load_explicit_context(directory, root)

    assert "context.md" in str(error.value)
    assert str(directory) not in str(error.value)


def test_rejects_symlink_context_using_only_its_basename(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "actual.md"
    target.write_text("sensitive source text", encoding="utf-8")
    alias = root / "alias.md"
    alias.symlink_to(target)

    with pytest.raises(InputError) as error:
        load_explicit_context(alias, root)

    assert "alias.md" in str(error.value)
    assert "sensitive source text" not in str(error.value)


def test_rejects_invalid_utf8_without_exposing_file_contents(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "binary.md"
    context.write_bytes(b"secret-token-value\xff")

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root)

    assert "binary.md" in str(error.value)
    assert "secret-token-value" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


def test_rejects_unsupported_context_extension(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "brief.pdf"
    context.write_text("raw-pdf-body", encoding="utf-8")

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root)

    assert "brief.pdf" in str(error.value)
    assert "raw-pdf-body" not in str(error.value)


def test_redacts_credential_bearing_context_filename_in_errors(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "token=real-provider-secret.pdf"
    context.write_text("raw-pdf-body", encoding="utf-8")

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root)

    assert "real-provider-secret" not in str(error.value)
    assert "[REDACTED]" in str(error.value)


def test_rejects_context_larger_than_byte_limit_without_reading_contents(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "large.txt"
    context.write_bytes(b"secret-data" * 20_000)

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root, max_bytes=200_000)

    assert "large.txt" in str(error.value)
    assert "secret-data" not in str(error.value)


def test_rejects_context_that_grows_after_initial_size_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "growing.txt"
    context.write_bytes(b"12345")
    original_fstat = context_module.os.fstat

    def hide_regular_file_growth(descriptor: int) -> os.stat_result | SimpleNamespace:
        details = original_fstat(descriptor)
        if stat.S_ISREG(details.st_mode):
            return SimpleNamespace(st_mode=details.st_mode, st_size=4)
        return details

    monkeypatch.setattr(context_module.os, "fstat", hide_regular_file_growth)

    with pytest.raises(InputError, match="exceeds"):
        load_explicit_context(context, root, max_bytes=4)


def test_rejects_unavailable_context_root_without_exposing_path(tmp_path: Path) -> None:
    missing_root = tmp_path / "private-root"

    with pytest.raises(InputError, match="context root") as error:
        load_explicit_context(missing_root / "brief.md", missing_root)

    assert str(missing_root) not in str(error.value)


def test_rejects_leaf_symlink_substituted_after_path_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "brief.md"
    context.write_text("approved brief", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("private outside content", encoding="utf-8")
    original_resolve = context_module.resolve_safe_path

    def validate_then_swap(path: Path, supplied_root: Path, *, must_exist: bool) -> Path:
        safe = original_resolve(path, supplied_root, must_exist=must_exist)
        context.unlink()
        context.symlink_to(outside)
        return safe

    monkeypatch.setattr(context_module, "resolve_safe_path", validate_then_swap)

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root)

    assert "brief.md" in str(error.value)
    assert "private outside content" not in str(error.value)


def test_rejects_parent_symlink_substituted_after_path_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    nested = root / "nested"
    nested.mkdir(parents=True)
    context = nested / "brief.md"
    context.write_text("approved brief", encoding="utf-8")
    held = root / "held"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "brief.md").write_text("private outside content", encoding="utf-8")
    original_resolve = context_module.resolve_safe_path

    def validate_then_swap(path: Path, supplied_root: Path, *, must_exist: bool) -> Path:
        safe = original_resolve(path, supplied_root, must_exist=must_exist)
        nested.rename(held)
        nested.symlink_to(outside, target_is_directory=True)
        return safe

    monkeypatch.setattr(context_module, "resolve_safe_path", validate_then_swap)

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root)

    assert "brief.md" in str(error.value)
    assert "private outside content" not in str(error.value)


def test_rejects_root_directory_substituted_after_path_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "brief.md"
    context.write_text("approved brief", encoding="utf-8")
    held = tmp_path / "held"
    original_resolve = context_module.resolve_safe_path

    def validate_then_swap(path: Path, supplied_root: Path, *, must_exist: bool) -> Path:
        safe = original_resolve(path, supplied_root, must_exist=must_exist)
        root.rename(held)
        root.mkdir()
        (root / "brief.md").write_text("private replacement content", encoding="utf-8")
        return safe

    monkeypatch.setattr(context_module, "resolve_safe_path", validate_then_swap)

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root)

    assert "brief.md" in str(error.value)
    assert "private replacement content" not in str(error.value)


def test_rejects_root_symlink_substituted_after_path_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "brief.md"
    context.write_text("approved brief", encoding="utf-8")
    held = tmp_path / "held"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "brief.md").write_text("private outside content", encoding="utf-8")
    original_resolve = context_module.resolve_safe_path

    def validate_then_swap(path: Path, supplied_root: Path, *, must_exist: bool) -> Path:
        safe = original_resolve(path, supplied_root, must_exist=must_exist)
        root.rename(held)
        root.symlink_to(outside, target_is_directory=True)
        return safe

    monkeypatch.setattr(context_module, "resolve_safe_path", validate_then_swap)

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root)

    assert "brief.md" in str(error.value)
    assert "private outside content" not in str(error.value)


def test_context_access_fails_closed_without_nofollow_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "brief.md"
    context.write_text("approved brief", encoding="utf-8")
    monkeypatch.delattr(os, "O_NOFOLLOW")

    with pytest.raises(InputError, match="unavailable"):
        load_explicit_context(context, root)
