# Security policy

## Supported version

Security fixes target the latest code on `main`. No published package or release artifact is
claimed until one appears in this repository's Releases page.

## Report a vulnerability

Use GitHub's **Security → Report a vulnerability** private-reporting flow for this repository.
If private reporting is unavailable, open a minimal issue requesting a secure contact channel;
do not include exploit details, credentials, personal data, or private context in a public issue.

Please include affected revision, impact, reproduction conditions, and a suggested mitigation
when possible. Allow maintainers time to assess and coordinate remediation before disclosure.

## Credential and data handling

- Never commit API keys, `.env` files, private context, generated reports containing private
  information, personal email addresses, local user paths, or session identifiers.
- Use a restricted provider key through `GOOGLE_API_KEY` only for an explicit Google run.
- The tool reads no context unless `--context-file` is supplied. Provider runs transmit the
  explicit question/context to the selected provider.
- Public examples and tests must remain fictional and sanitized.

The tracked-content privacy scan and full-history Gitleaks workflow are defense in depth, not a
guarantee that every possible secret or personal identifier will be detected.
