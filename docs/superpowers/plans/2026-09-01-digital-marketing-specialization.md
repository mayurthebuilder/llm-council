# Digital Marketing Specialization Implementation Plan

**Goal:** Reposition and finish the existing secure council as LLM Council for
Digital Marketing, with first-class AEO and GEO coverage.

**Design:** `docs/superpowers/specs/2026-09-01-digital-marketing-specialization.md`

## Task M1: Marketing domain defaults (TDD)

- Add failing tests for the five marketing advisor lenses and explicit SEO/AEO/GEO
  instructions.
- Replace generic advisor defaults with the approved marketing council.
- Preserve advisor IDs, schemas, anonymity, and orchestration contracts.

## Task M2: Marketing demo and CLI (TDD)

- Convert the interrupted CLI work from billing to a fictional B2B SaaS digital
  marketing launch.
- Add a sanitized `examples/digital-marketing-launch-context.md` and remove the
  billing example.
- Ensure help/notices say that demo output is fixed and simulated.
- Test JSON, Markdown, HTML, explicit context, safe failures, Google cleanup, and
  zero-network demo behavior.

## Task M3: Marketing evaluation fixtures

- Add deterministic cases for launch strategy, channel mix, SEO/AEO/GEO, and
  positioning.
- Assert required specialist coverage and evidence-gap language, not subjective
  marketing quality or business outcomes.

## Task M4: Professional public documentation and automation

- Write a marketing-focused README, architecture docs, security/contribution
  files, license, changelog, and GitHub templates.
- Add CI, privacy scanning, package/type marker, and reproducible demo output.
- Use current verified Google model and pinned action versions; make no unverified
  provider, coverage, traffic, citation, ranking, or revenue claims.

## Task M5: Release verification

- Run full tests, coverage, Ruff, mypy, package build, install/smoke tests, offline
  network guard, privacy scan, Gitleaks full history, and public GitHub verification.
- Run a live Google smoke test only if a key is already configured; otherwise state
  clearly that the adapter is mocked and offline-tested.
- Update the GitHub repository description to the approved digital-marketing
  positioning only after the branch passes all gates.

