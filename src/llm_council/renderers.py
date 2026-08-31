"""Canonical decision renderers and safe local output publishing."""

from __future__ import annotations

import html
import json
import os
import stat
import uuid
from pathlib import Path
from typing import Any

from .errors import OutputError
from .models import CouncilDecision
from .security import resolve_safe_path


def render_json(decision: CouncilDecision) -> str:
    """Return the deterministic, machine-readable representation of a decision."""

    return json.dumps(decision.model_dump(mode="json"), indent=2, sort_keys=True)


def render_markdown(decision: CouncilDecision) -> str:
    """Return a fixed, readable Markdown representation of a decision."""

    sections = [
        "# Council Decision",
        "",
        "## Recommendation",
        "",
        decision.recommendation,
        "",
        _markdown_list_section("Rationale", decision.rationale),
        _markdown_list_section("Consensus", decision.consensus),
        _markdown_list_section("Dissent", decision.dissent),
        _markdown_list_section("Assumptions", decision.assumptions),
        _markdown_list_section("Risks", decision.risks),
        _markdown_list_section("Next Actions", decision.next_actions),
        "## Decision Details",
        "",
        f"- Confidence: {decision.confidence}",
        f"- Advisor count: {decision.advisor_count}",
        f"- Review count: {decision.review_count}",
    ]
    if decision.execution_metadata:
        sections.extend(["", _markdown_list_section("Execution Metadata", _metadata_lines(decision))])
    return "\n".join(sections) + "\n"


def render_html(decision: CouncilDecision) -> str:
    """Return self-contained, accessible HTML rendered from fixed trusted markup."""

    metadata = ""
    if decision.execution_metadata:
        metadata = _html_section("Execution Metadata", _metadata_lines(decision))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Council Decision</title>
<style>
:root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #172033; background: #f4f7fb; }}
body {{ margin: 0; line-height: 1.55; }}
main {{ max-width: 56rem; margin: 0 auto; padding: 2rem 1rem 3rem; }}
article {{ background: #fff; border: 1px solid #dbe3ee; border-radius: .75rem; box-shadow: 0 .5rem 1.5rem #17203312; overflow: hidden; }}
header {{ padding: 2rem; background: #102a43; color: #fff; }}
header p {{ max-width: 44rem; margin-bottom: 0; }}
section {{ padding: 1.25rem 2rem; border-top: 1px solid #dbe3ee; }}
h1, h2 {{ line-height: 1.2; }} h1 {{ margin: 0; font-size: clamp(1.8rem, 5vw, 2.6rem); }} h2 {{ margin-top: 0; color: #102a43; }}
ul {{ padding-left: 1.25rem; }} li + li {{ margin-top: .45rem; }}
.details {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }}
.detail {{ margin: 0; padding: .75rem; border-radius: .5rem; background: #edf5ff; }}
.detail strong {{ display: block; font-size: .875rem; color: #486581; }}
@media (max-width: 38rem) {{ main {{ padding: 0; }} article {{ border-radius: 0; }} header, section {{ padding: 1.25rem; }} .details {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<main>
<article>
<header><h1>Council Decision</h1><p>{_escape(decision.recommendation)}</p></header>
{_html_section("Rationale", decision.rationale)}
{_html_section("Consensus", decision.consensus)}
{_html_section("Dissent", decision.dissent)}
{_html_section("Assumptions", decision.assumptions)}
{_html_section("Risks", decision.risks)}
{_html_section("Next Actions", decision.next_actions)}
<section aria-labelledby="details-title"><h2 id="details-title">Decision Details</h2><div class="details">
<p class="detail"><strong>Confidence</strong>{_escape(decision.confidence)}</p>
<p class="detail"><strong>Advisor count</strong>{decision.advisor_count}</p>
<p class="detail"><strong>Review count</strong>{decision.review_count}</p>
</div></section>
{metadata}
</article>
</main>
</body>
</html>
"""


def write_output(content: str, path: Path, root: Path, overwrite: bool = False) -> Path:
    """Atomically publish content inside root without a silent overwrite by default."""

    target = resolve_safe_path(path, root, must_exist=False)
    root_path = root.resolve(strict=False)
    parent_parts, target_name = _output_components(target, root_path)
    root_descriptor: int | None = None
    parent_descriptor: int | None = None
    temporary_name: str | None = None
    try:
        root_descriptor, parent_descriptor = _open_output_parent(root_path, parent_parts)
        if not _destination_is_current(root_path, root_descriptor, parent_descriptor, parent_parts):
            raise OutputError("Output destination changed during write.")
        if _entry_exists(parent_descriptor, target_name) and not overwrite:
            raise OutputError("Output file already exists.")

        temporary_name, descriptor = _create_temporary_file(parent_descriptor)
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        if not _destination_is_current(root_path, root_descriptor, parent_descriptor, parent_parts):
            raise OutputError("Output destination changed during write.")
        if _entry_exists(parent_descriptor, target_name) and not overwrite:
            raise OutputError("Output file already exists.")
        if overwrite:
            os.replace(
                temporary_name,
                target_name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
        else:
            _publish_without_replacing(temporary_name, target_name, parent_descriptor)
        temporary_name = None
        if not _destination_is_current(root_path, root_descriptor, parent_descriptor, parent_parts):
            _best_effort_unlink(target_name, parent_descriptor)
            raise OutputError("Output destination changed during write.")
        return target
    except OutputError:
        raise
    except (NotImplementedError, OSError, TypeError):
        raise OutputError("Unable to write output.") from None
    finally:
        if temporary_name is not None and parent_descriptor is not None:
            _best_effort_unlink(temporary_name, parent_descriptor)
        if parent_descriptor is not None:
            _close_descriptor(parent_descriptor)
        if root_descriptor is not None:
            _close_descriptor(root_descriptor)


def _output_components(target: Path, root: Path) -> tuple[tuple[str, ...], str]:
    """Return descriptor-safe parent and filename components for a validated target."""

    relative = target.relative_to(root)
    if not relative.parts or relative.name in {"", "."}:
        raise OutputError("Output path must name a file.")
    return relative.parts[:-1], relative.name


def _open_output_parent(root: Path, parent_parts: tuple[str, ...]) -> tuple[int, int]:
    """Open a root-pinned output parent without following symlink components."""

    directory_flags = _directory_flags()
    root_descriptor = os.open(root, directory_flags)
    parent_descriptor = os.dup(root_descriptor)
    try:
        for component in parent_parts:
            next_descriptor = os.open(component, directory_flags, dir_fd=parent_descriptor)
            _close_descriptor(parent_descriptor)
            parent_descriptor = next_descriptor
    except (NotImplementedError, OSError, TypeError):
        _close_descriptor(parent_descriptor)
        _close_descriptor(root_descriptor)
        raise OutputError("Unable to access output destination.") from None
    return root_descriptor, parent_descriptor


def _directory_flags() -> int:
    """Return the fail-closed flags needed for descriptor-relative directory traversal."""

    try:
        return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    except AttributeError:
        raise OutputError("Secure output paths are unavailable on this platform.") from None


def _create_temporary_file(parent_descriptor: int) -> tuple[str, int]:
    """Create a private sibling temporary file using the pinned parent descriptor."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    for _ in range(10):
        temporary_name = f".llm-council-{uuid.uuid4().hex}.tmp"
        try:
            descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_descriptor)
        except FileExistsError:
            continue
        except (NotImplementedError, OSError, TypeError):
            raise OutputError("Unable to write output.") from None
        return temporary_name, descriptor
    raise OutputError("Unable to reserve output storage.")


def _destination_is_current(
    root_path: Path, root_descriptor: int, parent_descriptor: int, parent_parts: tuple[str, ...]
) -> bool:
    """Confirm that the visible destination still names the pinned parent directory."""

    try:
        root_stat = os.stat(root_path, follow_symlinks=False)
        if (root_stat.st_dev, root_stat.st_ino) != _descriptor_identity(root_descriptor):
            return False
        visible_parent = os.dup(root_descriptor)
        try:
            for component in parent_parts:
                next_descriptor = os.open(component, _directory_flags(), dir_fd=visible_parent)
                _close_descriptor(visible_parent)
                visible_parent = next_descriptor
            return _descriptor_identity(visible_parent) == _descriptor_identity(parent_descriptor)
        finally:
            _close_descriptor(visible_parent)
    except (NotImplementedError, OSError, TypeError):
        return False


def _descriptor_identity(descriptor: int) -> tuple[int, int]:
    details = os.fstat(descriptor)
    return details.st_dev, details.st_ino


def _entry_exists(parent_descriptor: int, name: str) -> bool:
    """Check a leaf entry without following a target symlink."""

    try:
        details = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except (NotImplementedError, OSError, TypeError):
        raise OutputError("Unable to access output destination.") from None
    if stat.S_ISLNK(details.st_mode):
        raise OutputError("Output destination must not be a symlink.")
    if stat.S_ISDIR(details.st_mode):
        raise OutputError("Output path must name a file.")
    return True


def _publish_without_replacing(temporary_name: str, target_name: str, parent_descriptor: int) -> None:
    """Atomically create a new target without replacement inside one pinned directory."""

    try:
        os.link(
            temporary_name,
            target_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileExistsError:
        raise OutputError("Output file already exists.") from None
    except (NotImplementedError, OSError, TypeError):
        raise OutputError("Unable to write output.") from None
    _best_effort_unlink(temporary_name, parent_descriptor)


def _best_effort_unlink(name: str, parent_descriptor: int) -> None:
    """Remove a temporary or rolled-back entry without masking a completed publish."""

    try:
        os.unlink(name, dir_fd=parent_descriptor)
    except (NotImplementedError, OSError, TypeError):
        pass


def _close_descriptor(descriptor: int) -> None:
    """Close a descriptor without allowing cleanup failures to escape."""

    try:
        os.close(descriptor)
    except OSError:
        pass


def _markdown_list_section(title: str, values: list[str]) -> str:
    return f"## {title}\n\n" + "\n".join(f"- {value}" for value in values) + "\n"


def _metadata_lines(decision: CouncilDecision) -> list[str]:
    return [
        f"{key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
        for key, value in sorted(decision.execution_metadata.items())
    ]


def _html_section(title: str, values: list[str]) -> str:
    identifier = title.lower().replace(" ", "-")
    items = "\n".join(f"<li>{_escape(value)}</li>" for value in values)
    return f'<section aria-labelledby="{identifier}-title"><h2 id="{identifier}-title">{title}</h2><ul>{items}</ul></section>'


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)
