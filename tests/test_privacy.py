from __future__ import annotations

from pathlib import Path

from scripts.privacy_scan import find_privacy_issues


def test_privacy_scanner_detects_real_sensitive_shapes_without_literal_samples(
    tmp_path: Path,
) -> None:
    email = "person" + "@" + "example.com"
    user_path = "/" + "Users" + "/private-account/project/file.txt"
    session = "session" + "_id=abc123-private"
    sample = tmp_path / "sample.txt"
    sample.write_text(f"{email}\n{user_path}\n{session}", encoding="utf-8")

    findings = find_privacy_issues([sample])

    assert {finding.kind for finding in findings} == {
        "email address",
        "private user path",
        "session identifier",
    }


def test_privacy_scanner_accepts_public_documentation_rules(tmp_path: Path) -> None:
    sample = tmp_path / "safe.md"
    sample.write_text(
        "Do not commit Gmail addresses, private local paths, session identifiers, or API keys.",
        encoding="utf-8",
    )

    assert find_privacy_issues([sample]) == []


def test_package_includes_typing_marker() -> None:
    marker = Path(__file__).parents[1] / "src" / "llm_council" / "py.typed"

    assert marker.is_file()
