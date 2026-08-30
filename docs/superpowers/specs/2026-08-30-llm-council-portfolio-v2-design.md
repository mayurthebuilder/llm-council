# LLM Council Portfolio v2 — Design Specification

**Status:** Proposed for implementation  
**Date:** 2026-08-30  
**Repository:** `mayurthebuilder/llm-council`

## 1. Product goal

Build a portfolio-grade, provider-neutral decision engine that asks several independent AI advisors to analyze the same question, runs a blind peer-review round, and produces a structured chairman synthesis.

The project must be credible to hiring managers: easy to understand, safe to run, deterministic to test without paid API calls, and polished enough to demonstrate engineering judgment rather than only prompt orchestration.

## 2. Scope and non-goals

### In scope

- A Python 3.11+ package and command-line interface.
- Five configurable advisor roles running concurrently.
- Blind, randomized peer review that does not reveal provider or model identity.
- A chairman synthesis with recommendation, dissent, assumptions, risks, and next actions.
- Markdown, JSON, and safely escaped HTML output.
- Optional explicit context-file input with strict size and path controls.
- Provider adapters behind one interface, plus a deterministic fake provider for tests and demos.
- Unit, integration, security, CLI, and deterministic evaluation tests.
- CI quality gates, secret scanning, documentation, and a sanitized demo.

### Not in scope for v1

- Autonomous execution of decisions.
- Automatic browsing, retrieval, workspace scanning, or conversation-memory access.
- A hosted service that stores questions or outputs.
- Claims that a council answer is objectively correct or a substitute for professional advice.

## 3. User experience

Primary command:

```bash
llm-council run \
  --question "Should a small SaaS team build or buy its billing system?" \
  --context-file ./examples/billing-context.md \
  --format markdown \
  --output ./decision.md
```

Safe defaults:

- The question is required.
- Context is used only when the user explicitly supplies a file.
- Output goes to stdout unless an output path is explicitly supplied.
- No prompt, context, response, environment value, or API key is logged by default.
- A built-in deterministic demo mode works without credentials or network access.

## 4. Architecture

```text
CLI / Python API
       |
Input validation and explicit-context loader
       |
Council orchestrator
  |-- five concurrent advisor calls
  |-- response normalization
  |-- identity-blind peer-review round
  `-- chairman synthesis
       |
Structured CouncilDecision
       |
Markdown | JSON | escaped HTML renderer
```

### Components

1. **Domain models**
   - `CouncilRequest`: question, optional context, council configuration.
   - `AdvisorResult`: anonymous advisor ID, analysis, recommendation, assumptions, evidence references, risks.
   - `PeerReview`: reviewer ID, ranked response IDs, critique, missing evidence.
   - `CouncilDecision`: recommendation, rationale, consensus, dissent, confidence limits, risks, next actions, execution metadata.

2. **Provider interface**
   - One async protocol accepts a structured prompt and returns text.
   - Production adapters translate provider-specific APIs into the protocol.
   - The deterministic fake provider supports all tests and a no-key demonstration.
   - Optional provider dependencies remain isolated from the core package.

3. **Council orchestrator**
   - Runs advisors concurrently with per-call timeouts.
   - Assigns random anonymous response IDs before peer review.
   - Prevents an advisor from reviewing its own response.
   - Uses a configurable quorum so one provider failure does not automatically destroy a run.
   - Passes normalized reviews and advisor results to the chairman.

4. **Prompt boundary**
   - System instructions and user-supplied material are kept in separate structured fields.
   - Supplied context is explicitly labelled untrusted evidence, not executable instruction.
   - The chairman must surface dissent and missing evidence rather than manufacture agreement.

5. **Renderers**
   - JSON is the canonical machine-readable representation.
   - Markdown is the default human-readable output.
   - HTML is generated from trusted templates with strict escaping; raw model HTML is never injected.

## 5. Decision methodology

The default council uses complementary analytical lenses:

- Strategy and second-order effects
- Evidence quality and uncertainty
- Execution feasibility and cost
- Adversarial red-team critique
- Ethics, safety, and stakeholder risk

Each advisor receives the same evidence boundary and produces the same schema. Peer reviewers rank anonymous answers against explicit criteria: relevance, evidence use, logical quality, risk coverage, and actionability. The chairman receives the analyses plus reviews, but not provider identities.

The final decision must clearly separate:

- supplied facts;
- model inferences;
- unresolved assumptions;
- areas of consensus;
- material dissent;
- recommended next actions.

## 6. Security and privacy design

- Never search parent directories, home directories, editor state, chat transcripts, or unrelated workspace files.
- Accept context only through an explicit path; reject directories, symlinks escaping the working directory, unsupported encodings, and oversized files.
- Read credentials only from documented environment-variable names at adapter initialization.
- Never print, serialize, cache, or include credentials in exceptions.
- Redact credential-shaped values from diagnostic errors as defence in depth.
- Keep telemetry off by default; v1 has no persistent history store.
- Treat all model output and supplied context as untrusted text.
- Escape HTML output and prevent path traversal or silent overwrite of existing output files.
- Use sanitized fictional examples containing no personal email, local path, session URL, client data, or private identifier.
- Run Gitleaks across the complete public history in CI and before releases.

## 7. Failure handling

- A failed advisor call is captured as structured failure metadata without leaking request or credential data.
- A run continues only if the configured advisor quorum is met.
- A failed peer review can be omitted if the review quorum remains valid.
- Chairman failure returns a nonzero CLI exit and a concise remediation message.
- Rate limits, authentication failures, timeouts, malformed responses, and unavailable optional providers have distinct user-facing errors.
- Partial results are not written unless the user explicitly requests partial-output behavior.

## 8. Testing and evaluation strategy

All required tests run offline with the deterministic fake provider.

### Automated tests

- **Unit:** validation, anonymization, ranking normalization, quorum rules, renderers, redaction, and safe paths.
- **Integration:** complete advisor-review-chairman flow, concurrent execution, partial failure, timeout, and deterministic ordering.
- **CLI:** help, demo run, all formats, exit codes, explicit file output, and overwrite protection.
- **Security:** prompt-injection fixtures, HTML/script escaping, path traversal, symlink escape, secret-shaped error data, and scans for personal identifiers.
- **Evaluation:** sanitized decision scenarios with assertions for dissent, assumptions, risks, and actionable next steps.

### Quality gates

- `pytest` passes on supported Python versions.
- Core orchestration coverage target is at least 90%.
- Linting and type checking pass.
- Demo mode completes without network access.
- Gitleaks reports zero findings over full history.
- Fresh-clone installation and smoke test pass in CI.

Real-provider smoke tests are optional, manually triggered, and use repository secrets without printing them.

## 9. Professional presentation

The public repository will include:

- A concise README with problem, methodology, architecture, quick start, demo output, limitations, and CV-ready impact statement.
- Architecture and sequence diagrams that render natively on GitHub.
- Badges for CI, supported Python, license, and coverage when a coverage service is configured.
- `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, changelog, and issue/PR templates.
- A sanitized example decision and terminal recording or GIF generated from demo mode.
- A tagged `v1.0.0` release only after all gates pass.

No badge, benchmark, provider, or accuracy claim will be published unless it is reproducible from the repository.

## 10. Acceptance criteria

The implementation is ready to present when:

1. A fresh clone can install and run the deterministic demo using documented commands.
2. All offline tests and quality gates pass.
3. At least one real provider adapter is documented and can be enabled without changing core code.
4. Advisor identities are blinded during peer review and tested.
5. Failure and quorum behavior are visible and tested.
6. No personal Gmail address, private path, session URL, secret, or personal record exists anywhere in the public Git history.
7. The README explains what was built, why the architecture matters, and what remains deliberately out of scope.

## 11. Implementation sequence after approval

1. Scaffold package, tooling, CI, and domain models.
2. Implement the provider protocol and deterministic fake.
3. Implement orchestration using test-driven development.
4. Add renderers, CLI, failure handling, and security controls.
5. Add a production provider adapter and optional real-provider smoke test.
6. Build documentation, diagrams, sanitized demo, and contribution files.
7. Run the full test, security, privacy, and fresh-clone verification matrix.

