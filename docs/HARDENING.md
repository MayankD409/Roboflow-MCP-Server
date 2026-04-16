# Hardening Guide

Defaults are already strict. This guide is for operators who want to go
further — single-workspace scoping, an audit sink, tight quotas, and
tool-level allowlists.

## Picking a mode

`ROBOFLOW_MCP_MODE` controls the capability scope of every tool call:

| Mode | What it allows | What it blocks |
|------|----------------|----------------|
| `readonly` (default) | Reads: workspace inspection, project browse, image search | Every destructive op (tag removals, future deletes, training cancels) |
| `curate` | Everything in `readonly`, plus dataset writes (tag add/remove/set, uploads, deletes) | Quota-heavy ops (version creation, training submission) |
| `full` | Everything | Nothing — pair with an allow list for fine-grained control |

Pick the least privilege that works. If the LLM only needs to search and
tag, stay on `curate` and put `roboflow_remove_image_tags` on the deny list.

## Scoping to a single workspace

```bash
export ROBOFLOW_WORKSPACE=contoro
export ROBOFLOW_MCP_WORKSPACE_ALLOWLIST=contoro
```

With these two set, any tool call that resolves to a different workspace
raises `ToolDisabledError` **before** the HTTP request is built. The
allowlist is CSV: `ROBOFLOW_MCP_WORKSPACE_ALLOWLIST=contoro,acme`.

## Cutting the tool surface

Two env vars, both CSV:

- `ROBOFLOW_MCP_ALLOW_TOOLS` — if set, only tools in this list are
  registered. The rest don't appear in `list_tools` at all.
- `ROBOFLOW_MCP_DENY_TOOLS` — tools in this list are dropped. Deny wins
  over allow.

Example: "this server is for search only."

```bash
export ROBOFLOW_MCP_ALLOW_TOOLS=roboflow_get_workspace,roboflow_list_projects,roboflow_search_images
```

Now the LLM can see and call exactly those three tools. Tagging and
everything else is invisible.

## Destructive operations

`remove_image_tags` and `set_image_tags` are destructive. To run them you
need **both**:

1. `ROBOFLOW_MCP_MODE=curate` or `full`.
2. `confirm="yes"` passed as an explicit argument in the tool call.

The confirm token is intentionally a string the operator types, not a
boolean. An injected prompt that says "set `confirm=true`" won't satisfy
the check.

## Dry-run preview

Every tool accepts `dry_run=True`. When set, the tool returns the prepared
HTTP request (method, path, params with `api_key` redacted, body) without
contacting the Roboflow API. Useful for:

- Convincing yourself the LLM is about to do the right thing.
- Screenshotting a request for a bug report.
- Running a CI smoke test without burning quota.

```json
{
  "dry_run": true,
  "tool": "roboflow_add_image_tags",
  "method": "POST",
  "path": "/contoro/boxes/images/img_abc/tags",
  "params": {"api_key": "***"},
  "body": {"operation": "add", "tags": ["sku-42"]}
}
```

## Quotas and circuit breaker

The client has a two-window token bucket. Defaults are conservative:

| Env var | Default | What it does |
|---------|---------|--------------|
| `ROBOFLOW_MCP_RATE_LIMIT_PER_MINUTE` | 60 | Rolling 60 s window |
| `ROBOFLOW_MCP_RATE_LIMIT_PER_HOUR` | 1000 | Rolling 3600 s window |
| `ROBOFLOW_MCP_CIRCUIT_BREAKER_THRESHOLD` | 5 | Consecutive 5xx before the circuit opens |
| `ROBOFLOW_MCP_CIRCUIT_BREAKER_COOLDOWN` | 30.0 | Seconds the circuit stays open |

When a quota trips, callers see `QuotaExceededError` with a `retry_after`
hint. When the circuit opens, callers see `CircuitOpenError`. Neither
error counts against the retry budget — they fail fast.

4xx caller errors (401, 403, 404) don't trip the breaker; only transport
errors and 5xx responses do.

## Audit log

Set `ROBOFLOW_MCP_AUDIT_LOG=/var/log/roboflow-mcp.jsonl` to stream one
JSON object per tool call into a file. Schema:

```json
{
  "ts": 1713198000.123,
  "tool": "roboflow_search_images",
  "mode": "curate",
  "workspace": "contoro",
  "args_hash": "a1b2c3d4e5f60718",
  "outcome": "ok",
  "http_status": 200,
  "duration_ms": 187.4,
  "error_class": null
}
```

If unset, audit lines go to stderr so you still see them when running under
`uvx` or in a container.

The audit log never stores raw arguments — only a 16-char sha256 prefix of
the JSON-serialised args dict. Prompt-injection content, tag names,
filenames, and any other user-controlled string never reach the log.

## Rotating the API key

1. Generate a new key in the Roboflow web UI.
2. Update `ROBOFLOW_API_KEY` wherever the server reads its env (MCP
   client config, `.env` file, container secret, systemd drop-in).
3. Restart the server process.
4. Revoke the old key in the Roboflow UI.

The server doesn't cache the key outside of the `SecretStr` inside
`RoboflowSettings`, which is re-read at process start. There's no cache to
bust.

## Transport

Today the only transport is `stdio`. A Streamable HTTP transport lands in
v0.9 with its own set of knobs (OAuth 2.1 + PKCE, CORS allowlist, per-user
key vault). Until then, run the server as a local subprocess of the MCP
client and treat every tool call as happening under the operator's OS
identity.

If you absolutely need to proxy the Roboflow API through an HTTP
intermediary for a dev workflow:

```bash
export ROBOFLOW_API_URL=http://localhost:4000
export ROBOFLOW_MCP_ALLOW_INSECURE=1
```

Both variables are required; `ALLOW_INSECURE` is documented as dev-only
and prints a warning in future versions.

## Upload roots (v0.3+)

`roboflow_upload_image` and `roboflow_upload_images_batch` accept a
`{"kind":"path", ...}` source. The path **must** live under one of the
allowed roots set via `ROBOFLOW_MCP_UPLOAD_ROOTS` (CSV of absolute
directories). Every path is:

1. Rejected outright if it (or any parent) is a symlink.
2. Resolved with `Path.resolve(strict=True)` — the file must exist and
   be a regular file.
3. Checked against the list of allowed roots (after `resolve()` on
   each root).

If the variable is unset, path uploads are disabled entirely and the
tool raises `ImageGuardError`. URL and base64 uploads still work.

```bash
export ROBOFLOW_MCP_UPLOAD_ROOTS=/home/ops/datasets,/data/inbox
```

Every path upload also runs through the image-content guard (Pillow
verify + load, MIME whitelist, size/dimension caps, decompression-bomb
check).

## URL ingestion

`roboflow_upload_image` with `{"kind":"url", ...}` runs through the
SSRF guard before any fetch:

- Scheme allowlist: `https` only (`http` with `ROBOFLOW_MCP_ALLOW_INSECURE=1`).
- IP-range blocklist: RFC1918 (10/8, 172.16/12, 192.168/16), loopback,
  link-local (169.254/16, fe80::/10), multicast, IANA-reserved,
  unspecified, and all the cloud-metadata IPs (169.254.169.254,
  169.254.170.2, fd00:ec2::254).
- DNS-first: the hostname is resolved *before* the HTTP request so a
  DNS answer containing any blocked address rejects the whole fetch,
  even if it also returns a public IP.
- 25 MiB / 30 s caps on the download itself.

Residual risk: a DNS rebinding attack between our lookup and httpx's
internal resolution can swing the IP. Full mitigation (a custom httpx
transport that pins the resolved IP) lands in v0.5.

## Export downloads

`roboflow_download_export` is gated behind:

- `ROBOFLOW_MCP_ENABLE_DOWNLOADS=true` (default true — set to `false`
  to hard-disable downloads).
- `ROBOFLOW_MCP_MODE=curate` or `full`.
- `confirm="yes"` argument on every call.
- Writes go under `ROBOFLOW_MCP_EXPORT_CACHE_DIR` (default
  `~/.cache/roboflow-mcp`) unless the caller passes an explicit
  `dest_dir`.

Zip extraction (when `extract=True`) enforces a **zip-slip guard**:
every member is resolved against the extraction directory and rejected
if it escapes. See `tests/unit/tools/test_download.py::test_download_export_refuses_zip_slip`.

## Runbook: suspected leak

1. Rotate the Roboflow API key immediately.
2. Search the audit log for calls during the suspected leak window:
   `grep '"outcome":"ok"' audit.jsonl | tail -500`.
3. Compare the `args_hash` column across calls to identify repeats or odd
   cadence patterns.
4. File a report at `deshpandemayank5@gmail.com` per `SECURITY.md`.
