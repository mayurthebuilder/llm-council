# Contributing

Contributions that improve digital-marketing rigor, privacy, provider boundaries, or testability
are welcome. Recommendations about SEO, AEO, GEO, channels, attribution, or compliance must be
framed as testable guidance—not outcome guarantees.

## Setup

```bash
git clone https://github.com/mayurthebuilder/llm-council.git
cd llm-council
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Install `'.[google]'` only when working on the optional adapter. Tests must not require a key or
make generation calls.

## Quality gates

```bash
python -m pytest -q --cov=llm_council --cov-report=term-missing
python -m ruff check .
python -m mypy src
python scripts/privacy_scan.py
python -m build
```

Before opening a pull request:

1. Add a failing test first for every behavior change, then implement the smallest fix.
2. Keep examples fictional and deterministic; do not add private identifiers or credentials.
3. Update user-facing documentation and the changelog when behavior changes.
4. Explain which claims are supplied facts, inferences, assumptions, or missing evidence.
5. Confirm that outputs make no ranking, citation, traffic, lead, or revenue guarantee.

Use focused commits and complete the pull-request template. CI runs untrusted pull-request code
without repository secrets and with read-only token permissions.
