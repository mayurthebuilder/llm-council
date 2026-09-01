from __future__ import annotations

from pathlib import Path

import pytest

from scripts.normalize_demo_timing import normalize_timing


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            (
                "# Report\n\n- duration_seconds: 9.9\n\n"
                "## Execution Metadata\n\n- duration_seconds: 0.0123\n\n"
            ),
            (
                "# Report\n\n- duration_seconds: 9.9\n\n"
                "## Execution Metadata\n\n- duration_seconds: 0.0\n\n"
            ),
        ),
        (
            (
                "<p>duration_seconds: 9.9</p>"
                '<section aria-labelledby="execution-metadata-title"><ul>'
                "<li>advisor_duration_seconds: 1.2e-05</li></ul></section>\n"
            ),
            (
                "<p>duration_seconds: 9.9</p>"
                '<section aria-labelledby="execution-metadata-title"><ul>'
                "<li>advisor_duration_seconds: 0.0</li></ul></section>\n"
            ),
        ),
    ],
)
def test_timing_normalization_preserves_nonmetadata_content_and_trailing_newline(
    source: str, expected: str
) -> None:
    normalized = normalize_timing(source)

    assert normalized == expected


def test_public_docs_describe_untrusted_markdown_and_current_google_boundary() -> None:
    root = Path(__file__).parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    reproduction = (root / "examples" / "README.md").read_text(encoding="utf-8")

    assert "escaped Markdown" not in readme
    assert "Markdown preserves untrusted model text" in readme
    assert "industry labels" in readme
    assert "no special optimization, markup, or schema" in readme
    assert "foundational SEO and people-first content" in readme
    assert "AEO/GEO hacks" in readme
    assert "https://developers.google.com/search/docs/fundamentals/ai-optimization-guide" in readme
    assert reproduction.count("--overwrite") == 2
    assert "python scripts/normalize_demo_timing.py" in reproduction
