# Security Model

This is the threat model that guides the server's defences. Every feature PR
that changes an existing tool or adds a new one must either (a) fit one of
the mitigations below, or (b) explicitly call out a new threat that needs a
new mitigation.

Public issues are fine for design discussion; responsible disclosure lives
in [SECURITY.md](../SECURITY.md).

## Scope

- **In scope**: the MCP server process, the Roboflow API key it holds, the
  tools it exposes to an LLM, and any data the Roboflow API returns that
  might flow back into the LLM.
- **Out of scope**: the Roboflow service itself, the LLM client, the OS,
  the container runtime. We assume those are hardened separately.

## Trust boundaries

1. **Operator → server**: the human sets env vars, picks a mode, points at
   an API endpoint. We trust the operator.
2. **LLM → server (tool call)**: untrusted. The LLM may have been tricked by
   prompt injection in documents, email, web pages, or prior tool output.
3. **Roboflow API → server (response)**: untrusted. Image names, tag names,
   project descriptions, and workflow block outputs can carry adversarial
   content.
4. **Server → Roboflow API**: trusted direction; we control what we send,
   but we must not leak the API key in the URL, headers, or body.

## Threats

| ID | Threat | Severity | Mitigation(s) |
|----|--------|----------|---------------|
| T1 | Prompt injection via Roboflow-controlled strings (tag names, image names, project descriptions) steers the LLM into calling dangerous tools. | High | `safety.sanitize_untrusted` envelopes strings as `{"untrusted": "..."}` so well-behaved clients render them as data. Combined with T5/T6 mitigations: even if the LLM is steered, destructive tools remain gated. |
| T2 | API-key exfiltration via log leak, error message leak, or exception traceback. | Critical | `SecretStr` in `config.py`; `SecretScrubbingFormatter` with 20+ leak-vector fixture in `tests/unit/test_logging.py`; regex + literal scrub covers query param, Authorization/X-Api-Key headers, JSON and dict reprs. Every new log line must go through the root logger. |
| T3 | SSRF via user-provided image URLs on upload. | High | **Mitigation lands in v0.3** with `safety/urlguard.py`: `https://` only, block RFC1918/loopback/link-local/metadata IP ranges, DNS-resolve then pin. Until then, upload tools are not shipped. |
| T4 | Path traversal via local-file upload. | High | **v0.3**: `safety/imageguard.py` resolves with `Path.resolve(strict=True)` inside an operator-configured `ROBOFLOW_MCP_UPLOAD_ROOT`. Symlinks that escape the root are rejected. 25 MiB / 16384 px cap. |
| T5 | Over-permissioned tool invocation: LLM calls a destructive op (delete, remove tags, cancel training) without human-in-loop. | Critical | `ROBOFLOW_MCP_MODE` defaults to `readonly`. Destructive tools use the `@destructive` decorator: they refuse to run in `readonly` and require a literal `confirm="yes"` argument. Allow/deny lists (`ROBOFLOW_MCP_ALLOW_TOOLS` / `DENY_TOOLS`) can strip specific tools from registration entirely. |
| T6 | Tool poisoning: an injected prompt convinces the LLM to call `remove_image_tags(tags=["important"])` on the wrong image. | Critical | Same as T5, plus audit log (T9) and `dry_run=True` preview mode that returns the HTTP request shape without calling the API. Operators can deny the tool outright in sensitive workspaces. |
| T7 | Rate-limit abuse / denial-of-wallet: a runaway LLM loop burns through a workspace's Roboflow quota. | High | Client-side token bucket in `client.py`: default 60 req/min, 1000 req/hr, configurable via `ROBOFLOW_MCP_RATE_LIMIT_*`. Circuit breaker opens after N consecutive 5xx responses (default 5). 4xx caller errors don't trip the breaker. |
| T8 | Malformed image / PIL / polyglot-file exploits via the upload tool. | Medium | **v0.3**: Pillow `verify()` + `load()` in a subprocess with memory and timeout caps; MIME whitelist via `python-magic`. |
| T9 | Cross-workspace data bleed when the operator has access to multiple workspaces. | High | `ROBOFLOW_MCP_WORKSPACE_ALLOWLIST` — when set, any tool arg whose workspace isn't on the list raises `ToolDisabledError` before any HTTP call. `ROBOFLOW_WORKSPACE` serves as the default single-workspace scope. |
| T10 | Dependency supply-chain: typosquat of `mcp-server-roboflow` on PyPI, or a compromised upstream (`mcp`, `httpx`, `pydantic`, future `roboflow`). | High | Reserved `mcp-server-roboflow` on PyPI; trusted-publisher OIDC (no API token in the repo); Dependabot weekly scans; `pip-audit` + `bandit` + `gitleaks` + CodeQL in CI; SLSA-3 provenance + Sigstore signing on release artifacts (v0.2+). |
| T11 | Credentials-in-transit leak via misconfigured `ROBOFLOW_API_URL` (cleartext proxy). | Medium | `client.py` rejects non-`https://` URLs unless `ROBOFLOW_MCP_ALLOW_INSECURE=1`. The override is logged as a warning and documented as dev-only. |

## Non-threats (explicitly accepted)

- **A malicious operator** can always do whatever the Roboflow API key
  allows. We don't try to defend against the person running the server.
- **An LLM that ignores the `{"untrusted": ...}` convention** may still
  treat Roboflow strings as instructions. T1 is defence-in-depth, not a
  guarantee.
- **Local file-system access by the server process** is intentionally
  broad; upload tools (v0.3) add a scoped layer on top, but anything the
  Python process can read, an operator bug could read.

## Update procedure

1. If you change a security-relevant module (`client.py`, `guards.py`,
   `logging.py`, `audit.py`, anything under `safety/`), update this file
   in the same PR.
2. When a new threat is identified, add a row. Don't edit an existing row
   to cover something new — a new row forces a review.
3. Threats that become obsolete stay in the table with "retired" in the
   Mitigation column and a link to the PR that made them so.
