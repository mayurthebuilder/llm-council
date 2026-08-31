"""Canonical decision renderers and safe local output publishing."""

from __future__ import annotations

import html
import json
import os
import tempfile
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
    if target.exists() and not overwrite:
        raise OutputError("Output file already exists.")

    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".llm-council-", suffix=".tmp", dir=target.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        target = resolve_safe_path(target, root, must_exist=False)
        if target.exists() and not overwrite:
            raise OutputError("Output file already exists.")
        if overwrite:
            temporary_path.replace(target)
        else:
            _publish_without_replacing(temporary_path, target)
        temporary_path = None
        return target
    except OutputError:
        raise
    except OSError:
        raise OutputError("Unable to write output.") from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _publish_without_replacing(temporary_path: Path, target: Path) -> None:
    """Atomically create target from a sibling temporary file without replacement."""

    try:
        os.link(temporary_path, target)
    except FileExistsError:
        raise OutputError("Output file already exists.") from None
    except OSError:
        raise OutputError("Unable to write output.") from None
    temporary_path.unlink()


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
