from __future__ import annotations

from pathlib import Path

import pytest

from llm_council.context import load_explicit_context
from llm_council.errors import InputError


def test_loads_explicit_markdown_context_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "brief.md"
    context.write_text("# Decision brief\n\nUse only supplied facts.", encoding="utf-8")

    assert load_explicit_context(context, root) == "# Decision brief\n\nUse only supplied facts."


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


def test_rejects_unsupported_context_extension(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "brief.pdf"
    context.write_text("raw-pdf-body", encoding="utf-8")

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root)

    assert "brief.pdf" in str(error.value)
    assert "raw-pdf-body" not in str(error.value)


def test_rejects_context_larger_than_byte_limit_without_reading_contents(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = root / "large.txt"
    context.write_bytes(b"secret-data" * 20_000)

    with pytest.raises(InputError) as error:
        load_explicit_context(context, root, max_bytes=200_000)

    assert "large.txt" in str(error.value)
    assert "secret-data" not in str(error.value)
