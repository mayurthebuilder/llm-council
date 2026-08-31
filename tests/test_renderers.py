from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from llm_council import renderers
from llm_council.errors import OutputError
from llm_council.models import CouncilDecision
from llm_council.renderers import render_html, render_json, render_markdown, write_output


def _decision() -> CouncilDecision:
    return CouncilDecision(
        recommendation="Choose <script>alert('x')</script> & scale ☃.",
        rationale=["Markdown **must** remain readable & useful."],
        consensus=["Use a phased rollout."],
        dissent=["A bespoke service could retain control."],
        assumptions=["The launch date is fixed."],
        risks=["Vendor lock-in."],
        next_actions=["Run a two-week pilot."],
        confidence="moderate",
        advisor_count=3,
        review_count=2,
        execution_metadata={"budget": 12500.0, "ready": True},
    )


def test_json_renderer_round_trips_canonical_model_data() -> None:
    decision = _decision()

    rendered = render_json(decision)

    assert rendered == json.dumps(decision.model_dump(mode="json"), indent=2, sort_keys=True)
    assert CouncilDecision.model_validate_json(rendered) == decision


def test_markdown_renderer_preserves_readable_untrusted_text() -> None:
    rendered = render_markdown(_decision())

    assert "# Council Decision" in rendered
    assert "Choose <script>alert('x')</script> & scale ☃." in rendered
    assert "Markdown **must** remain readable & useful." in rendered
    assert "## Next Actions" in rendered


def test_html_renderer_escapes_untrusted_text_and_uses_only_fixed_markup() -> None:
    rendered = render_html(_decision())

    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; scale ☃." in rendered
    assert "<script>" not in rendered
    assert "<h1>Council Decision</h1>" in rendered
    assert "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">" in rendered


def test_html_renderer_escapes_hostile_execution_metadata_keys() -> None:
    decision = _decision()
    decision.execution_metadata["<img src=x onerror=alert(1)> & detail"] = 1

    rendered = render_html(decision)

    assert "&lt;img src=x onerror=alert(1)&gt; &amp; detail: 1" in rendered
    assert "<img src=x onerror=alert(1)>" not in rendered


def test_write_output_creates_content_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()

    output = write_output("decision", Path("report.md"), root)

    assert output == root / "report.md"
    assert output.read_text(encoding="utf-8") == "decision"


def test_write_output_refuses_an_existing_file_without_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "report.md"
    target.write_text("original", encoding="utf-8")

    with pytest.raises(OutputError, match="already exists"):
        write_output("replacement", target, root)

    assert target.read_text(encoding="utf-8") == "original"


def test_write_output_overwrites_only_when_explicitly_enabled(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "report.md"
    target.write_text("original", encoding="utf-8")

    output = write_output("replacement", target, root, overwrite=True)

    assert output == target
    assert target.read_text(encoding="utf-8") == "replacement"


def test_write_output_rejects_parent_traversal_without_creating_files(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()

    with pytest.raises(OutputError, match="inside the working directory"):
        write_output("decision", Path("../private.md"), root)

    assert not (tmp_path / "private.md").exists()


def test_write_output_rejects_a_symlink_target_without_partial_file(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    actual = root / "actual.md"
    actual.write_text("original", encoding="utf-8")
    alias = root / "alias.md"
    alias.symlink_to(actual)

    with pytest.raises(OutputError, match="alias.md"):
        write_output("replacement", alias, root, overwrite=True)

    assert actual.read_text(encoding="utf-8") == "original"
    assert list(root.glob(".llm-council-*.tmp")) == []


def test_write_output_cleans_temporary_file_when_target_appears_during_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "report.md"
    original_link = os.link

    def create_target_then_link(source: str | bytes, destination: str | bytes, *args: object, **kwargs: object) -> None:
        target.write_text("racing writer", encoding="utf-8")
        original_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", create_target_then_link)

    with pytest.raises(OutputError, match="already exists"):
        write_output("decision", target, root)

    assert target.read_text(encoding="utf-8") == "racing writer"
    assert list(root.glob(".llm-council-*.tmp")) == []


def test_write_output_rejects_parent_symlink_swap_during_temporary_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    nested = root / "nested"
    external = tmp_path / "external"
    nested.mkdir(parents=True)
    external.mkdir()
    held = root / "held"
    original_open = os.open
    swapped = False

    def swap_before_descriptor_relative_create(
        name: str | bytes,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if not swapped and dir_fd is not None and flags & os.O_CREAT:
            nested.rename(held)
            nested.symlink_to(external, target_is_directory=True)
            swapped = True
        if dir_fd is None:
            return original_open(name, flags, mode)
        return original_open(name, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(renderers.os, "open", swap_before_descriptor_relative_create)

    with pytest.raises(OutputError):
        write_output("decision", Path("nested/report.md"), root)

    assert swapped
    assert not (external / "report.md").exists()
    assert list(external.glob(".llm-council-*.tmp")) == []
    assert list(held.glob(".llm-council-*.tmp")) == []


def test_write_output_rejects_parent_symlink_swap_during_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    nested = root / "nested"
    external = tmp_path / "external"
    nested.mkdir(parents=True)
    external.mkdir()
    held = root / "held"
    original_link = os.link
    swapped = False

    def swap_before_descriptor_relative_link(
        source: str | bytes,
        destination: str | bytes,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal swapped
        if not swapped and "src_dir_fd" in kwargs and "dst_dir_fd" in kwargs:
            nested.rename(held)
            nested.symlink_to(external, target_is_directory=True)
            swapped = True
        original_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(renderers.os, "link", swap_before_descriptor_relative_link)

    output = write_output("decision", Path("nested/report.md"), root)

    assert swapped
    assert output == nested / "report.md"
    assert not (external / "report.md").exists()
    assert (held / "report.md").read_text(encoding="utf-8") == "decision"
    assert list(external.glob(".llm-council-*.tmp")) == []
    assert list(held.glob(".llm-council-*.tmp")) == []


def test_write_output_ignores_temporary_cleanup_failure_after_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    original_unlink = os.unlink

    def fail_temporary_cleanup(path: str | bytes, *args: object, **kwargs: object) -> None:
        if Path(path).name.startswith(".llm-council-"):
            raise OSError("cleanup failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(renderers.os, "unlink", fail_temporary_cleanup)

    output = write_output("decision", Path("report.md"), root)

    assert output == root / "report.md"
    assert output.read_text(encoding="utf-8") == "decision"


def test_write_output_never_deletes_another_writers_leaf_after_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    nested = root / "nested"
    external = tmp_path / "external"
    nested.mkdir(parents=True)
    external.mkdir()
    held = root / "held"
    target = nested / "report.md"
    original_link = os.link
    replaced = False

    def replace_leaf_then_swap_parent(
        source: str | bytes,
        destination: str | bytes,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal replaced
        original_link(source, destination, *args, **kwargs)
        replacement = nested / "replacement.md"
        replacement.write_text("other writer", encoding="utf-8")
        replacement.replace(target)
        nested.rename(held)
        nested.symlink_to(external, target_is_directory=True)
        replaced = True

    monkeypatch.setattr(renderers.os, "link", replace_leaf_then_swap_parent)

    try:
        output = write_output("decision", Path("nested/report.md"), root)
    except OutputError:
        output = nested / "report.md"

    assert replaced
    assert output == nested / "report.md"
    assert not (external / "report.md").exists()
    assert (held / "report.md").read_text(encoding="utf-8") == "other writer"
