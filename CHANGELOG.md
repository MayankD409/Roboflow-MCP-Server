# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-04-16

### Added
- **Capability model** (`ROBOFLOW_MCP_MODE`): three scopes — `readonly`
  (default), `curate`, `full`. Destructive tools refuse to run in
  `readonly` and require a literal `confirm="yes"` argument even in
  `curate`/`full`. Implemented via `@destructive` decorator in
  `src/roboflow_mcp/guards.py`.
- **Tool allow/deny lists**: `ROBOFLOW_MCP_ALLOW_TOOLS` and
  `ROBOFLOW_MCP_DENY_TOOLS` (both CSV). Tools excluded by these lists
  aren't registered at all and don't appear in `list_tools` responses.
- **Workspace allowlist** (`ROBOFLOW_MCP_WORKSPACE_ALLOWLIST`, CSV): any
  tool arg whose workspace isn't listed raises `ToolDisabledError` before
  any HTTP call, guarding against cross-workspace data bleed.
- **Dry-run preview**: every v0.1 tool now accepts `dry_run=True` and
  returns the prepared HTTP request (method, path, params with `api_key`
  redacted, body) without calling the Roboflow API.
- **JSONL audit log** (`src/roboflow_mcp/audit.py`): one line per tool
  call to the path in `ROBOFLOW_MCP_AUDIT_LOG` (stderr if unset). Records
  `ts`, `tool`, `mode`, `workspace`, sha256 `args_hash`, `outcome`,
  `http_status`, `duration_ms`, `error_class`. Raw arguments are never
  written — only the 16-char hash prefix.
- **Client-side quotas**: two-window token bucket (60 req/min, 1000 req/hr
  by default) raises `QuotaExceededError` with a `retry_after` hint.
  Configurable via `ROBOFLOW_MCP_RATE_LIMIT_PER_MINUTE` and
  `ROBOFLOW_MCP_RATE_LIMIT_PER_HOUR`.
- **Circuit breaker**: opens after 5 consecutive 5xx responses (default),
  stays open for 30 s, then allows a single probe. 4xx caller errors
  don't trip the breaker. Tunable via
  `ROBOFLOW_MCP_CIRCUIT_BREAKER_THRESHOLD` and `_COOLDOWN`.
- **Strict TLS**: `ROBOFLOW_API_URL` must start with `https://`. Plain
  HTTP is rejected unless `ROBOFLOW_MCP_ALLOW_INSECURE=1` is set for dev
  against a trusted local proxy.
- **Prompt-injection envelope**: new `roboflow_mcp.safety.sanitize_untrusted`
  helper wraps Roboflow-origin strings as `{"untrusted": "...", "truncated": bool}`
  with an 8 KiB byte cap so MCP clients render them as data rather than
  instructions.
- **Input bounds**: `validate_bounds` (guards.py) and configurable
  `ROBOFLOW_MCP_MAX_STRING_LENGTH` (default 4096) /
  `ROBOFLOW_MCP_MAX_LIST_LENGTH` (default 1000) enforced on every v0.1
  tool's inputs before the HTTP call.
- **PyPI Trusted Publisher** (OIDC): pushing a `v*.*.*` tag publishes to
  PyPI in the same workflow that creates the GitHub Release. No API token
  lives in the repo.
- **SLSA-3 provenance + Sigstore signing + CycloneDX SBOM** attached to
  every GitHub Release.
- **Cross-platform CI**: macOS and Windows matrices at Python 3.12
  alongside the existing Linux × Python {3.10, 3.11, 3.12, 3.13} matrix.
- **Security scans in CI**: `bandit`, `pip-audit`, `gitleaks`, and a
  separate **CodeQL** workflow (push + PR + weekly cron).
- Docs: `docs/SECURITY_MODEL.md` (11-threat table), `docs/HARDENING.md`
  (operator configuration guide), `docs/INSTALL.md` (install snippets for
  Claude Code, Claude Desktop, Cursor, Continue, Windsurf, Zed, VS Code).
- `SECURITY.md` expanded with GitHub private vulnerability reporting link,
  72 h ack SLA, 90-day coordinated-disclosure window, and supply-chain
  posture.

### Changed
- **Secret scrubber is now structured** (`src/roboflow_mcp/logging.py`).
  It covers 20+ leak vectors: query params, Authorization / X-Api-Key /
  X-Auth-Token headers (Bearer/Token/literal schemes, mixed casing), JSON
  bodies with `api_key` / `apiKey` / `auth_token` keys, Python dict
  repr output, and literal secrets from the config. Tested against a
  leak-vector fixture that new cases should be added to.
- `__version__` is now read from installed package metadata via
  `importlib.metadata.version("mcp-server-roboflow")`; a single bump in
  `pyproject.toml` is authoritative.
- `RoboflowSettings` defaults `mode=readonly`, which means the v0.1
  destructive tools (`roboflow_remove_image_tags`,
  `roboflow_set_image_tags`) now require explicit opt-in before they can
  be called. This is a **breaking change** in behaviour — not signature —
  for existing deployments that relied on destructive ops working by
  default.
- `build_server` accepts an optional `audit` parameter so tests can swap
  in an in-memory `AuditLogger`; production callers keep the default
  behaviour.
- `docs/RELEASING.md` reflects the single-source-of-version + Trusted
  Publisher wiring; the old "not yet wired up" TODO section is gone.

### Removed
- `roboflow>=1.1` is no longer a runtime dependency (nothing imported
  it). It will return as an optional `[sdk]` extra when the v0.3 dataset
  download tooling needs it.

### Security
- See `docs/SECURITY_MODEL.md` for the mapping from threats to
  mitigations. This release closes T2 (key exfil), T5 (over-permissioned
  tool invocation), T6 (tool poisoning), T7 (rate-limit / denial-of-wallet),
  T9 (cross-workspace bleed), T10 (supply-chain), and T11 (cleartext
  credentials). T3/T4/T8 are deferred to v0.3 when upload tools land; T1
  has a partial mitigation via `sanitize_untrusted` and becomes
  load-bearing in v0.3+.

## [0.1.1] - 2026-04-15

### Fixed
- Release workflow: restrict attached assets to `*.whl` and `*.tar.gz` so the
  `.gitignore` `uv build` writes into `dist/` is no longer uploaded to the
  GitHub Release.

### Changed
- `docs/RELEASING.md` now documents the AA (add/add) conflicts that appear
  on the `main` -> `develop` back-merge and shows the one-liner that
  resolves them by taking main's side.

## [0.1.0] - 2026-04-15

First public release. The server is usable end to end for dataset curation
against a real Roboflow workspace.

### Added
- Project scaffold with Git Flow branching, CI across Python 3.10-3.13,
  issue and PR templates, contributor docs, and the Apache-2.0 license.
- Foundation layer: typed errors (`RoboflowMCPError` and friends), env-driven
  settings with `SecretStr` masking, a secret-scrubbing log formatter, an
  async Roboflow HTTP client with auto-auth and exponential-backoff retry,
  and a FastMCP server skeleton.
- Workspace tools `roboflow_get_workspace` and `roboflow_list_projects`.
  Both wrap `GET /{workspace}`, honour `ROBOFLOW_WORKSPACE` as a default,
  and return typed pydantic models.
- Image search and tagging: `roboflow_search_images` with `tag`,
  `class_name`, and semantic `prompt` filters, plus
  `roboflow_add_image_tags`, `roboflow_remove_image_tags`, and
  `roboflow_set_image_tags`. Enough for the full "find, tag, find again"
  workflow that drives tag-based dataset curation.

### Fixed
- `ImageSummary.created` now accepts an int or a string. Roboflow's docs
  claim the field is a string, but the live search endpoint returns a
  Unix-millisecond int (e.g. `1715286185986`). Caught against a real
  workspace during v0.1 verification.

[Unreleased]: https://github.com/MayankD409/Roboflow-MCP-Server/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/MayankD409/Roboflow-MCP-Server/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/MayankD409/Roboflow-MCP-Server/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/MayankD409/Roboflow-MCP-Server/releases/tag/v0.1.0
