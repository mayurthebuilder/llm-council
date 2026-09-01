"""Scan every tracked UTF-8 file for personal-data and session-shaped values."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PrivacyFinding:
    """A location and category without reproducing the sensitive value."""

    path: Path
    line: int
    kind: str


_PATTERNS = {
    "email address": re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "private user path": re.compile(r"(?:^|[\s\"'=(])/(?:Users|home)/[^/\s\"']+/"),
    "session identifier": re.compile(
        r"(?:\bsession[_-]?id\b\s*[:=]\s*[^\s,;]+|"
        r"https?://(?:chatgpt\.com/c|claude\.ai/chat)/[0-9A-Za-z-]+)",
        re.IGNORECASE,
    ),
}


def find_privacy_issues(paths: Iterable[Path]) -> list[PrivacyFinding]:
    """Return sensitive-shape locations from readable UTF-8 text files."""

    findings: list[PrivacyFinding] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in _PATTERNS.items():
                if pattern.search(line):
                    findings.append(PrivacyFinding(path=path, line=line_number, kind=kind))
    return findings


def tracked_files(root: Path) -> list[Path]:
    """List repository-tracked files without broad exclusions."""

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / Path(item.decode()) for item in result.stdout.split(b"\0") if item]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = find_privacy_issues(tracked_files(root))
    if not findings:
        print("Privacy scan passed: no sensitive personal-data shapes in tracked UTF-8 files.")
        return 0
    for finding in findings:
        relative = finding.path.relative_to(root)
        print(f"{relative}:{finding.line}: {finding.kind}", file=sys.stderr)
    print(f"Privacy scan failed with {len(findings)} finding(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
