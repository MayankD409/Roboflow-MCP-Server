# Security Policy

## Supported versions

Only the latest minor release on `main` receives security fixes while the
project is pre-`1.0`. After `1.0`, the two most recent minors will be
supported.

## Reporting a vulnerability

**Please do not open a public issue for security problems.** Use one of:

1. **GitHub private vulnerability reporting** (preferred):
   https://github.com/MayankD409/Roboflow-MCP-Server/security/advisories/new
2. **Email**: `deshpandemayank5@gmail.com`

Include:

- A description of the issue and its impact.
- Steps to reproduce or a proof of concept.
- Any suggested fix, if you have one.
- An affected version or commit SHA.

You should get an acknowledgement within **72 hours**. If the report is
valid, we will agree on a disclosure timeline before any public
discussion. Our default coordinated-disclosure window is **90 days** from
acknowledgement, shortened if a fix ships sooner.

## Security model

For the threat model this codebase defends against, see
[docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md). For operator-facing
hardening, see [docs/HARDENING.md](docs/HARDENING.md).

## Handling secrets

This server requires a Roboflow private API key. Never commit it, never
log it, never paste it in issues. The server scrubs the key from logs and
error output through a structured redactor covering 20+ leak vectors
(query params, Authorization/X-Api-Key/X-Auth-Token headers, JSON bodies,
Python dict reprs). If you ever see a key leak through, report it as a
vulnerability.

When a key may have been exposed:

1. Rotate it in the Roboflow web UI.
2. Update the key everywhere the server reads it.
3. Restart the server.
4. Revoke the old key.

See the runbook in [docs/HARDENING.md](docs/HARDENING.md#runbook-suspected-leak).

## Supply-chain

- Published via PyPI **Trusted Publisher** (OIDC); no long-lived API
  token lives in the repository.
- Release artifacts (wheel + sdist) are **Sigstore-signed** and carry
  **SLSA-3 provenance**. A **CycloneDX SBOM** is attached to every GitHub
  Release.
- CI runs `bandit`, `pip-audit`, `gitleaks`, and **CodeQL** on every PR.
- Dependencies are updated weekly by Dependabot; actions are pinned to
  commit SHAs on the `main` branch.

## Out of scope

- The Roboflow service itself.
- The LLM client you plug the server into.
- Operator-level access to the machine running the server.

See the non-threats section of
[docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md#non-threats-explicitly-accepted)
for more detail.
