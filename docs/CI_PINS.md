# CI action pinning

This project pins every GitHub Actions `uses:` to a full 40-character
commit SHA rather than a tag like `@v4`. Tags are mutable — an upstream
maintainer (or attacker with push access) can re-tag a compromised
commit and every workflow using `@v4` picks it up on the next run.
SHAs are immutable.

## Format

Pin with the SHA followed by a human-readable version comment:

```yaml
uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
```

Dependabot is configured (see `.github/dependabot.yml`) to bump these
on the same weekly cadence as `pip` deps and preserves the trailing
version comment automatically.

## Why

- **OSSF Scorecard**: the `pinned-dependencies` check rewards SHA
  pinning — a requirement for the silver-tier OpenSSF Best Practices
  badge we're aiming at for v1.0.
- **`tj-actions/changed-files` incident (March 2025)**: a widely-used
  action had its `v35` and `v45` tags retagged to a malicious commit
  that exfiltrated secrets. Every SHA-pinned consumer was safe. Every
  `@v35`-pinned consumer leaked.
- **Deterministic CI**: a passing run today will keep passing next
  month unless we explicitly bump.

## Exceptions

Two workflows reference something other than a SHA. Both are deliberate.

### `pypa/gh-action-pypi-publish@release/v1`

PyPA explicitly recommends the rolling `release/v1` reference for their
Trusted Publisher flow. The action publishes wheels to PyPI via OIDC
and also handles Sigstore attestations; pinning to a specific SHA would
stop receiving security fixes to the publish path and can break the
attestation protocol as it evolves. See:
https://docs.pypi.org/trusted-publishers/using-a-publisher/

### `slsa-framework/slsa-github-generator/.../generator_generic_slsa3.yml@v2.0.0`

This is a reusable workflow (not a JavaScript action). SLSA's own
documentation requires pinning to a specific tag rather than a SHA,
because the generator validates its own provenance against the tag and
looks up metadata keyed on the tag string. Dependabot still bumps this
across major versions when new SLSA levels ship.

## Audit log

When adding a new action, run:

```bash
gh api repos/<owner>/<repo>/commits/<tag> --jq '.sha'
```

...and paste the resulting SHA with a `# <tag>` trailing comment. If
the action is JavaScript-based and Node-version-sensitive, also check
its release notes for the current Node runtime (today, Node 24 is the
minimum for new actions because Node 20 is deprecated after
September 16 2026).

Currently pinned:

| Action | Version | Notes |
|---|---|---|
| `actions/checkout` | v6.0.2 | |
| `astral-sh/setup-uv` | v7.6.0 | Dependabot will propose v8 separately |
| `codecov/codecov-action` | v6.0.0 | |
| `gitleaks/gitleaks-action` | v2.3.9 | |
| `actions/upload-artifact` | v5.0.0 | bumped from v4 for Node 24 runtime |
| `actions/download-artifact` | v5.0.0 | bumped from v4 for Node 24 runtime |
| `softprops/action-gh-release` | v2.6.2 | |
| `github/codeql-action/{init,autobuild,analyze}` | v3.35.2 | |

## v0.2 lesson — branch-protection status checks

When v0.2 renamed the CI matrix jobs to include the OS
(`lint + typecheck + test (ubuntu-latest, 3.10)` vs. the old
`lint + typecheck + test (3.10)`), the required-status-check contexts
on `main`'s branch protection rule did **not** auto-update. Every PR
from that point forward was unmergeable until we PATCHed the protection
rule via `gh api`.

**Rule**: before renaming or removing any CI job in a PR, update the
required contexts in the same PR. The easiest path is:

```bash
gh api -X PATCH \
  repos/<owner>/<repo>/branches/main/protection/required_status_checks \
  --input - <<'JSON'
{
  "strict": true,
  "contexts": [
    "lint + typecheck + test (ubuntu-latest, 3.10)",
    ...
  ]
}
JSON
```

Capture the full list of current contexts with:

```bash
gh api repos/<owner>/<repo>/branches/main/protection/required_status_checks \
  --jq '.contexts'
```

## v0.2 lesson — `packages-dir` in `pypa/gh-action-pypi-publish`

The PyPI publisher action runs `twine check` on **every** file in
`packages-dir` before uploading. Non-distribution artifacts (SBOM,
SLSA provenance) must not live under the same directory or twine will
reject them as `InvalidDistribution`. Keep `dist/` pure and write
auxiliary artifacts to sibling directories (`sbom/`, `provenance/`).
