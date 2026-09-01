"""Normalize only variable timing metadata in checked-in demo reports."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_TIMING_VALUE = re.compile(
    r"(?P<prefix>\b[A-Za-z0-9_]*duration_seconds:\s*)"
    r"(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
)
_MARKDOWN_METADATA = "\n## Execution Metadata\n\n"
_HTML_METADATA = '<section aria-labelledby="execution-metadata-title">'
_HTML_SECTION_END = "</section>"


def normalize_timing(content: str) -> str:
    """Replace duration values only inside a rendered execution-metadata section."""

    if _MARKDOWN_METADATA in content:
        before, marker, metadata = content.partition(_MARKDOWN_METADATA)
        return before + marker + _TIMING_VALUE.sub(r"\g<prefix>0.0", metadata)

    if _HTML_METADATA in content:
        before, marker, remainder = content.partition(_HTML_METADATA)
        metadata, section_end, after = remainder.partition(_HTML_SECTION_END)
        if section_end:
            metadata = _TIMING_VALUE.sub(r"\g<prefix>0.0", metadata)
        return before + marker + metadata + section_end + after

    return content


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize *_duration_seconds values in generated demo reports."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Generated report path(s).")
    arguments = parser.parse_args()
    for path in arguments.paths:
        content = path.read_text(encoding="utf-8")
        path.write_text(normalize_timing(content), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
